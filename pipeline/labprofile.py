import yaml

from . import paths

REVIEW_FIELDS = {"safe_edge_percent", "bleed", "color_space", "ppi"}
RENDER_FIELDS = {"submission_format", "jpeg_quality", "embed_icc", "max_file_bytes",
                 "filename_rules", "strip_metadata_beyond_allowlist", "keep_capture_date"}
ORDER_FIELDS = {"lab_color_correction", "checkout_crop_review"}

_ALL_FIELDS = REVIEW_FIELDS | RENDER_FIELDS | ORDER_FIELDS

DEFAULT_PROFILE = "generic-v1"


def active():
    """Name of the repo's active lab profile.

    The single source of truth, deliberately. The approval fingerprint
    (recipe.fingerprint) and the artifact dependency hashes (provenance)
    both resolve the lab through here; if they could name different
    profiles, a photo would be approved against one lab's review fields
    while its artifacts were invalidated against another's.
    """
    return DEFAULT_PROFILE


def load(name):
    f = paths.config_dir() / "lab-profiles" / f"{name}.yaml"
    if not f.exists():
        raise ValueError(f"no lab profile {name}")
    p = yaml.safe_load(f.read_text())
    if not isinstance(p, dict):
        raise ValueError(f"lab profile {name} is not a mapping: {type(p).__name__}")
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
