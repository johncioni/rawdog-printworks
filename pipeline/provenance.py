import hashlib
import json
from pathlib import Path

from . import labprofile, paths, recipe, render, toolchain


def gather_material(stem):
    return {
        "style_hashes": render.style_hashes(stem),
        "seed_hash": render.seed_hash(),
        "lock": json.loads((paths.config_dir() / "toolchain.lock").read_text()),
        "lab": labprofile.load(labprofile.active()),
        "preview_hashes": {style: content_hash(_preview_path(stem, style))
                           for style in paths.STYLES},
    }


def _canonical_sha(obj):
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def style_input_hash(stem, style, rec, material=None):
    material = material or gather_material(stem)
    return _canonical_sha({
        "raw": rec["raw_sha256"],
        "style": material["style_hashes"][style],
        "seed": material["seed_hash"],
        "render_tools": toolchain.entries_for(material["lock"],
                                              toolchain.RENDER_TOOLS),
        "overrides": rec["overrides"],
    })


def content_hash(path):
    # Deliberately uncached: a size+mtime cache would let a same-size,
    # restored-mtime swap return a stale hash (spec §4.2 forbids exactly that).
    path = Path(path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _preview_path(stem, style):
    return paths.previews_dir() / f"{stem}_{style}_preview.jpg"


def record_preview(rec, stem, style, preview_path, inputs_hash):
    rec.setdefault("previews", {})[style] = {
        "inputs": inputs_hash,
        "content": content_hash(preview_path),
    }


def stale_styles(stem, rec, material=None):
    material = material or gather_material(stem)
    stored = rec.get("previews") or {}
    stale = []
    for style in paths.STYLES:
        entry = stored.get(style)
        if (entry is None
                or entry.get("inputs") != style_input_hash(stem, style, rec,
                                                           material)
                or entry.get("content") != material["preview_hashes"][style]):
            stale.append(style)
    return sorted(stale)


def review_revision(stem, rec, material=None):
    material = material or gather_material(stem)
    fp = recipe.fingerprint(stem, rec, material["style_hashes"],
                            material["seed_hash"], material["lock"],
                            material["lab"])
    return "sha256:" + _canonical_sha({"fp": fp,
                                       "previews": material["preview_hashes"]})
