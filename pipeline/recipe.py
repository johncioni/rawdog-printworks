import hashlib
import json
import math
import os
import tempfile

import yaml

from . import labprofile, paths, toolchain

DEFAULT_SHARPEN = {"native": "0x0.8+0.6+0.008",
                   "8x10": "0x1.0+0.8+0.01",
                   "5x7": "0x0.9+0.9+0.01"}


def new(stem, raw_sha256, width, height, *, delivery_id=None,
        ingested_at=None):
    data = {"raw_sha256": raw_sha256,
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
    # Set only when supplied, so a flag-less ingest still writes byte-identical
    # legacy recipes.
    if delivery_id is not None:
        data["delivery_id"] = delivery_id
    if ingested_at is not None:
        data["ingested_at"] = ingested_at
    return data


def _path(stem):
    return paths.recipes_dir() / f"{stem}.yaml"


def save(stem, data):
    # Write-temp + replace: a reader never sees a half-written recipe, and a
    # crash mid-write leaves the previous recipe intact rather than truncated.
    p = _path(stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(yaml.safe_dump(data, sort_keys=True))
        os.replace(tmp, p)
    except BaseException:
        os.unlink(tmp)
        raise


def load(stem):
    return yaml.safe_load(_path(stem).read_text())


def file_hashes(paths_list):
    out = {}
    for p in paths_list:
        # Keying by basename alone would let two same-named files in different
        # directories collapse into one entry, dropping an input from the
        # fingerprint silently. No caller here passes duplicates legitimately.
        if p.name in out:
            raise ValueError(f"duplicate basename in file_hashes: {p.name}")
        out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _canonical(value, path):
    """Reject anything JSON would silently flatten or render non-canonically.

    JSON stringifies mapping keys, so {1: "x"} and {"1": "x"} would hash alike
    and let an approval survive a real change to the recipe. yaml.safe_load
    produces such keys from a hand-edited file, so this is reachable state.
    """
    if isinstance(value, dict):
        for k in value:
            if not isinstance(k, str):
                raise ValueError(
                    f"non-string mapping key at {path}: {k!r} ({type(k).__name__})")
        return {k: _canonical(v, f"{path}.{k}") for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}: {value!r}")
    return value


def _check_crops(crops):
    """Crop windows are normalized geometry; only finite real numbers hash."""
    for crop, window in crops.items():
        if window is None:
            continue
        for k, v in window.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(
                    f"crop {crop} field {k} is not a number: {v!r}")
            if not math.isfinite(v):
                raise ValueError(f"crop {crop} field {k} is not finite: {v!r}")


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
    _check_crops(rec["crops"])
    # Validate before dumping: sort_keys=True on mixed-type keys raises
    # TypeError, which would mask the specific problem being reported.
    material = _canonical(material, "material")
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()
