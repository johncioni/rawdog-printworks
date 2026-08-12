import hashlib
import json
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from . import paths

RENDER_TOOLS = {"rawtherapee", "rt_icc"}
CROP_TOOLS = {"magick", "font"}
PDF_TOOLS = {"img2pdf"}
VERIFY_TOOLS = {"qpdf", "pdfimages", "pdfinfo", "exiftool"}

# rawtherapee-cli 5.12 has no zero-exit version flag (--version exits 2, -v and
# -h exit 255); bare invocation exits 0 and prints the version banner first.
_VERSION_ARGS = {"rawtherapee": [], "magick": ["--version"],
                 "img2pdf": ["--version"], "qpdf": ["--version"],
                 "exiftool": ["-ver"], "pdfimages": ["-v"], "pdfinfo": ["-v"]}

_ASSET_NAMES = ("font", "rt_icc")

_FONT = "/System/Library/Fonts/Helvetica.ttc"
_RT_RESOURCES = "/Applications/RawTherapee.app/Contents/Resources"
_RT_VERSION = "5.12"

# Informational only: recorded for reproducibility, in no tool class, so a
# Python or test-dependency upgrade never invalidates rendered artifacts.
_INFO_PACKAGES = ("pytest", "pyyaml")
_INFORMATIONAL = {"python", *_INFO_PACKAGES}

_COMMENT = (
    "RawTherapee is pinned to 5.12. The 5.13 cask requires macOS >= 26; "
    "reinstall from the official 5.12 GitHub release, which is notarized "
    "(no quarantine handling needed). Never copy anything into "
    "/Applications/RawTherapee.app: it ships its own CLI and modifying the "
    "bundle breaks the code signature."
)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tool_path(name):
    return paths.rt_cli() if name == "rawtherapee" else shutil.which(name)


def _rt_icc_path():
    # The CLI on PATH is standalone, so the profile is not under its prefix
    # when the app bundle is installed; only fall back if the bundle is absent.
    base = Path(_RT_RESOURCES)
    if not base.is_dir():
        base = Path(paths.rt_cli()).parent.parent
    hits = sorted(base.rglob("RTv4_sRGB*"))
    if not hits:
        raise RuntimeError(f"RTv4_sRGB output profile not found under {base}")
    return hits[0]


def _version_output(path, args, name):
    # Executable is not enough: the in-bundle RT CLI is executable but SIGTRAPs
    # (rc -5, no output), so a failed or silent probe counts as the tool being
    # absent.
    try:
        out = subprocess.run([path, *args], capture_output=True, text=True)
    except OSError as e:
        raise RuntimeError(f"tool not found: {name} ({e})")
    text = ((out.stdout or "") + (out.stderr or "")).strip()
    if out.returncode != 0 or not text:
        raise RuntimeError(
            f"tool not found: {name} at {path} (version probe exit {out.returncode})")
    return text.splitlines()[0].strip()


def _package_version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def _tool_entry(name, args):
    p = _tool_path(name)
    if not p or not Path(p).exists():
        raise RuntimeError(f"tool not found: {name}")
    version = _version_output(p, args, name)
    if name == "rawtherapee" and _RT_VERSION not in version:
        raise RuntimeError(
            f"rawtherapee is not {_RT_VERSION} (PATH shadowing?): {version}")
    return {"path": p, "version": version, "sha256": _sha256(p)}


def _asset_entry(name):
    p = Path(_FONT) if name == "font" else _rt_icc_path()
    if not p.exists():
        raise RuntimeError(f"asset not found: {name} at {p}")
    return {"path": str(p), "version": "asset", "sha256": _sha256(p)}


def _probe_all():
    """Discover everything, collecting per-name failures instead of raising."""
    entries, failures = {}, {}
    for name, args in _VERSION_ARGS.items():
        try:
            entries[name] = _tool_entry(name, args)
        except RuntimeError as e:
            failures[name] = str(e)
    for name in _ASSET_NAMES:
        try:
            entries[name] = _asset_entry(name)
        except RuntimeError as e:
            failures[name] = str(e)
    entries["python"] = {"path": sys.executable, "version": platform.python_version()}
    for name in _INFO_PACKAGES:
        entries[name] = {"version": _package_version(name)}
    entries["_comment"] = _COMMENT
    return entries, failures


def discover():
    """Full discovery, raising on any failure. Used to generate the lock."""
    entries, failures = _probe_all()
    if failures:
        raise RuntimeError("; ".join(failures.values()))
    return entries


def write_lock(entries, lock_path):
    Path(lock_path).write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")


def verify(lock_path):
    want = json.loads(Path(lock_path).read_text())
    try:
        # Honors a monkeypatched discover(); falls back to the tolerant probe so
        # a broken tool becomes a structured problem naming it, letting the
        # caller tell verify-tool drift from render-tool drift.
        have, failures = discover(), {}
    except RuntimeError:
        have, failures = _probe_all()
    problems = []
    for name, entry in sorted(want.items()):
        # Only the comment and the named informational entries are hashless.
        if name.startswith("_") or name in _INFORMATIONAL:
            continue
        if not isinstance(entry, dict) or not entry.get("sha256"):
            problems.append({"name": name, "problem": "malformed lock entry"})
        elif name in failures:
            problems.append({"name": name, "problem": f"missing: {failures[name]}"})
        elif name not in have:
            problems.append({"name": name, "problem": "missing"})
        elif have[name]["sha256"] != entry["sha256"]:
            problems.append({"name": name, "problem": "hash mismatch "
                             f"({entry['version']} -> {have[name]['version']})"})
    return problems


def entries_for(lock, names):
    return {k: lock[k] for k in sorted(names) if k in lock}
