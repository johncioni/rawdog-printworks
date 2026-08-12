import hashlib
import json

import yaml

from . import labprofile, paths, toolchain

DEFAULT_SHARPEN = {"native": "0x0.8+0.6+0.008",
                   "8x10": "0x1.0+0.8+0.01",
                   "5x7": "0x0.9+0.9+0.01"}


def new(stem, raw_sha256, width, height):
    return {"raw_sha256": raw_sha256,
            "width": width,
            "height": height,
            # Normalized 0..1 windows (geometry.centered_crop_norm) or None, so
            # a recipe stays valid if the source is re-decoded at another size.
            "crops": {"8x10": None, "5x7": None},
            "overrides": {"denoise": False},
            "sharpen": dict(DEFAULT_SHARPEN),
            "expression_audit": [],
            # Non-empty puts the photo outside automated re-render.
            "manual_assets": [],
            "approval": {"fingerprint": None, "approved_at": None}}


def _path(stem):
    return paths.recipes_dir() / f"{stem}.yaml"


def save(stem, data):
    _path(stem).write_text(yaml.safe_dump(data, sort_keys=True))


def load(stem):
    return yaml.safe_load(_path(stem).read_text())


def file_hashes(paths_list):
    out = {}
    for p in paths_list:
        out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def fingerprint(stem, rec, style_hashes, seed_hash, lock, lab):
    material = {"stem": stem,
                "raw": rec["raw_sha256"],
                "crops": rec["crops"],
                "overrides": rec["overrides"],
                "sharpen": rec["sharpen"],
                "manual_assets": rec["manual_assets"],
                "styles": style_hashes,
                "seed": seed_hash,
                "render_tools": toolchain.entries_for(lock, toolchain.RENDER_TOOLS),
                "lab_review": labprofile.review_view(lab)}
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
