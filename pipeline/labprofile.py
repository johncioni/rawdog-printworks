import yaml

from . import paths

REVIEW_FIELDS = {"safe_edge_percent", "bleed", "color_space", "ppi"}
RENDER_FIELDS = {"submission_format", "jpeg_quality", "embed_icc", "max_file_bytes",
                 "filename_rules", "strip_metadata_beyond_allowlist", "keep_capture_date"}
ORDER_FIELDS = {"lab_color_correction", "checkout_crop_review"}

_ALL_FIELDS = REVIEW_FIELDS | RENDER_FIELDS | ORDER_FIELDS


def load(name):
    f = paths.config_dir() / "lab-profiles" / f"{name}.yaml"
    if not f.exists():
        raise ValueError(f"no lab profile {name}")
    p = yaml.safe_load(f.read_text())
    missing = _ALL_FIELDS - set(p)
    if missing:
        raise ValueError(f"lab profile {name} missing fields: {sorted(missing)}")
    unknown = set(p) - _ALL_FIELDS
    if unknown:
        raise ValueError(f"lab profile {name} unknown fields: {sorted(unknown)}")
    return p


def review_view(p):
    return {k: p[k] for k in sorted(REVIEW_FIELDS)}


def render_view(p):
    return {k: p[k] for k in sorted(RENDER_FIELDS)}


def check_filename(name, p):
    if len(name) > 64:
        return f"{name}: exceeds 64 chars"
    if not name.isascii():
        return f"{name}: non-ASCII"
    return None
