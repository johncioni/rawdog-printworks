import time

from . import (manifest, paths, pp3, provenance, publish, recipe, toolchain)


def _rel(path):
    try:
        return str(path.relative_to(paths.root()))
    except ValueError:
        return str(path)


def _control(stem, style, section, key, cast):
    side = pp3.Pp3.load(paths.sidecars_dir() / f"{stem}_{style}.pp3")
    value = side.get(section, key)
    if value is not None:
        return {"value": cast(value), "source": "sidecar"}
    base = pp3.Pp3.load(paths.config_dir() / "styles" / f"{style}.pp3")
    value = base.get(section, key)
    if value is not None:
        return {"value": cast(value), "source": "style"}
    return {"value": None, "source": "camera"}


def _photo(stem, m):
    rec = recipe.load(stem)
    # One recipe load + one material gather per photo; the fingerprint is
    # computed from THIS rec, never a re-read (coherence with review_revision).
    material = provenance.gather_material(stem)
    fingerprint = recipe.fingerprint(
        stem, rec, material["style_hashes"], material["seed_hash"],
        material["lock"], material["lab"])
    previews, hashes = {}, {}
    for style in paths.STYLES:
        p = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
        # Existence derives from the SAME snapshot as the hashes — a fresh
        # p.exists() could disagree with them mid-mutation.
        hashes[style] = material["preview_hashes"][style]
        previews[style] = _rel(p) if hashes[style] is not None else None
    crops = {c: w for c, w in rec["crops"].items() if w is not None}
    published = {"version": None, "path": None, "artifact_count": None}
    current = paths.output_dir() / "photos" / stem / "current"
    if current.is_symlink():
        import json as _json
        prov = current / "provenance.json"
        published["version"] = current.resolve().name
        published["path"] = _rel(current)
        if prov.exists():
            published["artifact_count"] = len(
                _json.loads(prov.read_text()).get("artifacts", {}))
    return {
        "stem": stem,
        "state": manifest.effective_state(m, stem, fingerprint),
        "delivery_id": rec.get("delivery_id"),
        "ingested_at": rec.get("ingested_at"),
        "review_revision": provenance.review_revision(stem, rec, material),
        "previews": previews,
        "preview_hashes": hashes,
        "stale_previews": provenance.stale_styles(stem, rec, material),
        "adjustments": {
            style: {
                # A hand-edited sidecar may carry `Temperature=5650.0`; bare
                # int() would raise and fail the whole status snapshot.
                "temperature": _control(stem, style, "White Balance",
                                        "Temperature",
                                        lambda value: int(float(value))),
                "exposure": _control(stem, style, "Exposure",
                                     "Compensation", float),
            }
            for style in paths.STYLES
        },
        "crops": crops,
        "expression_audit": rec.get("expression_audit", []),
        "published": published,
    }


def _state_stamps():
    stamps = {p: p.stat().st_mtime_ns
              for p in paths.recipes_dir().glob("*.yaml")}
    m = paths.manifest_path()
    stamps[m] = m.stat().st_mtime_ns if m.exists() else None
    return stamps


def snapshot():
    for attempt in (0, 1):
        stamps = _state_stamps()
        m = manifest.load_readonly()
        problems = toolchain.verify(paths.config_dir() / "toolchain.lock")
        result = {
            "repo": str(paths.root()),
            "toolchain": {"ok": problems == [], "failures": problems},
            "lock": publish.lock_status(),
            "styles": list(paths.STYLES),
            "photos": [_photo(stem, m) for stem in sorted(m["photos"])],
        }
        if _state_stamps() == stamps or attempt == 1:
            return result
        time.sleep(0.1)
