import json

import yaml

from . import labprofile, paths, toolchain

STATES = ("ingested", "preview_ready", "review_required", "approved",
          "rendered", "verified")

# Earlier states carry no promise about the rendered tree, so a fingerprint
# change cannot invalidate them; only these can be downgraded.
_APPROVED_OR_LATER = {"approved", "rendered", "verified"}


def load():
    p = paths.manifest_path()
    if p.exists():
        return json.loads(p.read_text())
    # A lost .manifest with recipes on disk is recoverable state, not an empty
    # repo: rebuilding beats silently re-ingesting approved photos.
    if any(paths.recipes_dir().glob("*.yaml")):
        return rebuild()
    return {"photos": {}}


def save(m):
    paths.manifest_path().write_text(json.dumps(m, indent=2, sort_keys=True))


def set_state(m, stem, state):
    if state not in STATES:
        raise ValueError(state)
    m["photos"].setdefault(stem, {"state": None, "fingerprint": None})
    m["photos"][stem]["state"] = state


def effective_state(m, stem, current_fp):
    ph = m["photos"].get(stem)
    if ph is None:
        return None
    if ph["state"] in _APPROVED_OR_LATER and ph.get("fingerprint") != current_fp:
        return "review_required"
    return ph["state"]


def artifact_names(stem, landscape_map=None):
    names = [f"{stem}_{s}.tif" for s in paths.STYLES]
    for s in paths.STYLES:
        names.append(f"{stem}_{s}.jpg")
        for c in paths.CROPS:
            names.append(f"{stem}_{s}_{c}.jpg")
    names += [n[:-4] + ".pdf" for n in names if n.endswith(".jpg")]
    names.append(f"{stem}_comparison.pdf")
    return names


def _parse(stem, artifact):
    """Split an artifact name into (style, crop), anchored on the stem.

    Substring matching would misread a stem that itself contains a style or
    crop token (e.g. "DSC_bw_001"), so only the segments after the stem count.
    """
    prefix = f"{stem}_"
    if not artifact.startswith(prefix):
        raise ValueError(f"artifact {artifact!r} does not belong to stem {stem!r}")
    parts = artifact[len(prefix):].rsplit(".", 1)[0].split("_")
    style = parts[0] if parts[0] in paths.STYLES else None
    crop = parts[1] if len(parts) > 1 and parts[1] in paths.CROPS else None
    return style, crop


def artifact_deps(stem, artifact, rec, style_hashes, seed_hash, lock, lab,
                  crop_geometry):
    style, crop = _parse(stem, artifact)
    sheet = artifact.endswith("_comparison.pdf")
    base = {"raw": rec["raw_sha256"], "seed": seed_hash,
            "style": style_hashes.get(style),
            "overrides": rec["overrides"],
            "render_tools": toolchain.entries_for(lock, toolchain.RENDER_TOOLS)}
    if artifact.endswith(".tif"):
        return base
    base["lab_render"] = labprofile.render_view(lab)
    # render_view omits ppi because it is review-class for approval purposes,
    # but ppi still sets the pixel dimensions of every raster we export.
    base["ppi"] = lab["ppi"]
    # Only the sheet draws text, so the font belongs to the sheet alone;
    # charging it to every JPG and PDF would stale them all on a font update.
    base["crop_tools"] = toolchain.entries_for(
        lock, toolchain.CROP_TOOLS if sheet else {"magick"})
    base["crop"] = crop_geometry if crop else None
    base["sharpen"] = rec["sharpen"][crop or "native"] if style else None
    if artifact.endswith(".pdf"):
        base["pdf_tools"] = toolchain.entries_for(lock, toolchain.PDF_TOOLS)
    if sheet:
        # Source filenames are constants, so recording them alone would leave
        # the sheet fresh while its inputs moved. Embedding each source's whole
        # record makes anything that stales a source stale the sheet too.
        base["sources"] = {n: artifact_deps(stem, n, rec, style_hashes,
                                            seed_hash, lock, lab, None)
                           for n in (f"{stem}_{s}.jpg" for s in paths.STYLES)}
    return base


def record_artifacts(m, stem, deps_by_name):
    m["photos"][stem]["artifacts"] = deps_by_name


def stale_artifacts(m, stem, current):
    stored = m["photos"].get(stem, {}).get("artifacts", {})
    return sorted(n for n, d in current.items() if stored.get(n) != d)


def rebuild():
    """Reconstruct .manifest from recipes and published provenance only."""
    m = {"photos": {}}
    for rp in sorted(paths.recipes_dir().glob("*.yaml")):
        stem = rp.stem
        rec = yaml.safe_load(rp.read_text())
        fp = (rec.get("approval") or {}).get("fingerprint")
        prov_p = paths.output_dir() / "photos" / stem / "current" / "provenance.json"
        m["photos"][stem] = {"state": "ingested", "fingerprint": fp,
                             "artifacts": {}}
        if prov_p.exists():
            prov = json.loads(prov_p.read_text())
            if fp and prov.get("fingerprint") == fp:
                m["photos"][stem].update(state="verified",
                                         artifacts=prov.get("artifacts", {}))
                continue
        if fp:
            m["photos"][stem]["state"] = "approved"
    save(m)
    return m
