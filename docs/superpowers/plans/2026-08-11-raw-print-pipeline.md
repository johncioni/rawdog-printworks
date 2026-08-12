# RAW → Print-Ready Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable pipeline that turns Panasonic GH7 `.rw2` files in `Input/` into 22 verified print-ready outputs per photo (3 TIF masters, 9 JPGs, 10 PDFs), with a human-in-the-loop visual review gate.

**Architecture:** A Python package (`pipeline/`) driven by `scripts/process.sh`, orchestrating external tools: rawtherapee-cli (RAW decode with layered plain-text `.pp3` profiles: committed base style + per-image override), ImageMagick (crops/resample/sharpen/JPG), img2pdf (lossless PDF wrap), exiftool (metadata), qpdf + poppler (PDF QA). State lives in committed per-photo recipes plus a derived gitignored `.manifest`; publishes are immutable `vNNN` dirs behind an atomically-swapped `current` symlink.

**Tech Stack:** Python 3 (venv, pytest, PyYAML), zsh entrypoint, Homebrew-installed image tools.

## Global Constraints

Copied from spec (`docs/superpowers/specs/2026-08-11-raw-print-pipeline-design.md`, rev 6):

- All deliverables sRGB. TIF masters: 16-bit, Deflate/zip compression, native pixels, native 4:3 ratio only.
- JPG: quality 92, 300 PPI tags. Crops resample to EXACT pixels: 8×10 → 2400×3000 (portrait) / 3000×2400 (landscape); 5×7 → 1500×2100 / 2100×1500. Native JPG: no resampling. All resampling is downsampling, Lanczos. Never upscale.
- Output sharpening AFTER the final resample, scaled to final pixel size.
- PDFs wrap JPGs via img2pdf with zero re-encoding; page box exactly equals print size (native PDFs: pixels ÷ 300 PPI; comparison sheet: US Letter).
- Naming: `<stem>_<style>[_<crop>].<ext>`; styles `natural|filmic|bw`; crops `8x10|5x7` (native = no crop token).
- rawtherapee-cli: explicit `-p` chains only (base style then per-image override), never `-d`; isolated config via `XDG_CONFIG_HOME` pointed at a run-copy of `config/rawtherapee-seed/`.
- File count per photo: 3 TIF + 9 JPG + 9 PDF + 1 comparison-sheet PDF = 22.
- Deliverable metadata allowlist (descriptive namespaces EXIF/XMP/IPTC/MakerNotes/PDF-Info only): Orientation, ExposureTime, FNumber, ISO, FocalLength, LensModel, DateTimeOriginal, optional Copyright, plus resolution tags. Everything else in those namespaces stripped and asserted absent. ICC profile and structural tags preserved.
- Oversized output (> lab profile `max_file_bytes`) FAILS verification for manual resolution; quality is never silently lowered.
- Driver takes an exclusive lockfile (`run/driver.lock`); single instance only.
- Tool paths: `RT_CLI = /Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli`; others on PATH from Homebrew.
- Python: `.venv/bin/python`, tests with `.venv/bin/python -m pytest`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Visual verification steps require the worker to Read the referenced image file and describe what they see; "looks plausible" without reading the file is a task failure.

## File Structure

```
scripts/process.sh            # thin zsh entrypoint → .venv python -m pipeline
pipeline/__init__.py
pipeline/__main__.py          # argparse CLI: status/ingest/preview/render/verify/publish/views
pipeline/paths.py             # repo-root-relative path constants + tool paths
pipeline/labprofile.py        # lab profile load/validate + field classes
pipeline/geometry.py          # pure crop/resample math
pipeline/toolchain.py         # toolchain.lock generate/verify
pipeline/recipe.py            # recipe YAML I/O + approval fingerprint
pipeline/manifest.py          # state machine + artifact dependency records
pipeline/ingest.py            # preflight + archive
pipeline/render.py            # RT/magick/img2pdf invocations → staging
pipeline/metadata.py          # strip + allowlist assertion
pipeline/verify.py            # QA suite
pipeline/publish.py           # lockfile, vNNN, current-swap, views, recovery
config/lab-profiles/generic-v1.yaml
config/styles/{natural,filmic,bw}.pp3
config/rawtherapee-seed/options
tests/test_{labprofile,geometry,toolchain,recipe,manifest,ingest,metadata,publish}.py
tests/conftest.py             # tmp-repo fixture
```

Each module is import-pure (no side effects at import); subprocess calls are isolated in `render.py`, `ingest.py`, `metadata.py`, `verify.py`, `toolchain.py` so pure logic stays unit-testable.

---

### Task 1: Checkpoint 1 — install tools and verify GH7 decode (GATE)

Nothing else may be built until this passes. No code in this task.

**Files:** none created (findings go in the commit message of Task 2).

- [ ] **Step 1: Install tools**

```bash
brew install --cask rawtherapee
brew install exiftool imagemagick img2pdf qpdf poppler
```

Expected: all succeed. If the rawtherapee cask fails, download the official dmg from rawtherapee.com and install to /Applications, then continue.

- [ ] **Step 2: Verify CLI presence and versions**

```bash
"/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli" --version
exiftool -ver && magick --version | head -1 && img2pdf --version && qpdf --version && pdfimages -v 2>&1 | head -1
```

Expected: every command prints a version. Record them.

- [ ] **Step 3: Neutral decode of one GH7 file**

```bash
mkdir -p previews
"/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli" \
  -o previews/checkpoint_neutral.jpg -j92 -Y -c Input/P1036163.rw2
```

Expected: exit 0, `previews/checkpoint_neutral.jpg` exists, and `magick identify previews/checkpoint_neutral.jpg` reports approximately 5776x4336 (or rotated equivalent). If rawtherapee-cli cannot decode the RW2 (error mentioning unsupported format), STOP the plan and report — the spec's fallback chain (darktable, then rawpy) triggers a re-plan.

- [ ] **Step 4: Visual verification (Read the JPG)**

Read `previews/checkpoint_neutral.jpg`. Confirm and write down: (a) subjects are recognizable people with plausible skin tones — no magenta/green cast indicating a broken color matrix; (b) orientation is correct (people upright); (c) no gross artifacts (banding, stuck tiles).

- [ ] **Step 5: Lens correction + highlight behavior check**

```bash
printf '[LensProfile]\nLcMode=lcp\nUseDistortion=true\nUseVignette=true\nUseCA=true\n' > /tmp/lens_on.pp3
"/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli" \
  -o previews/checkpoint_lens.jpg -j92 -Y -p /tmp/lens_on.pp3 -c Input/P1036163.rw2
```

Expected: exit 0. Read `previews/checkpoint_lens.jpg` and compare with the neutral: edges/corners may shift slightly (distortion correction applied) — identical output is acceptable for MFT lenses whose corrections are already embedded, but a hard error is not. Repeat Steps 3–4 for `Input/P1036170.rw2` (second aspect/mode sample). Record all findings for the Task 2 commit message.

### Task 2: Scaffolding — venv, package skeleton, entrypoint, first test

**Files:**
- Create: `scripts/process.sh`, `pipeline/__init__.py`, `pipeline/__main__.py`, `pipeline/paths.py`, `requirements-dev.txt`, `tests/conftest.py`, `tests/test_cli.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `pipeline.paths.ROOT` (pathlib.Path repo root), `paths.RT_CLI` (str), `paths.INPUT/OUTPUT/ARCHIVE/STAGING/RUN/RECIPES/SIDECARS/PREVIEWS/CONFIG` (Paths); CLI entry `python -m pipeline <subcommand>`.

- [ ] **Step 1: Create venv and requirements**

```bash
python3 -m venv .venv && .venv/bin/pip -q install pytest pyyaml
printf 'pytest\npyyaml\n' > requirements-dev.txt
printf '.venv/\n__pycache__/\n' >> .gitignore
```

- [ ] **Step 2: Write the failing test**

`tests/conftest.py`:
```python
import shutil, subprocess, sys
from pathlib import Path
import pytest

@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """A throwaway repo layout for tests that touch the filesystem."""
    for d in ("Input", "Output", "archive", "staging", "run", "recipes",
              "sidecars", "previews", "config/lab-profiles", "config/styles",
              "config/rawtherapee-seed"):
        (tmp_path / d).mkdir(parents=True)
    monkeypatch.setenv("PIPELINE_ROOT", str(tmp_path))
    return tmp_path
```

`tests/test_cli.py`:
```python
import subprocess, sys

def test_cli_status_runs():
    p = subprocess.run([sys.executable, "-m", "pipeline", "status"],
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert "photos" in p.stdout.lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL — `No module named pipeline`.

- [ ] **Step 4: Write minimal implementation**

`pipeline/__init__.py`: empty file.

`pipeline/paths.py`:
```python
import os
from pathlib import Path

ROOT = Path(os.environ.get("PIPELINE_ROOT", Path(__file__).resolve().parent.parent))
RT_CLI = "/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli"

INPUT = ROOT / "Input"
OUTPUT = ROOT / "Output"
ARCHIVE = ROOT / "archive"
STAGING = ROOT / "staging"
RUN = ROOT / "run"
RECIPES = ROOT / "recipes"
SIDECARS = ROOT / "sidecars"
PREVIEWS = ROOT / "previews"
CONFIG = ROOT / "config"
MANIFEST = ROOT / ".manifest"
STYLES = ("natural", "filmic", "bw")
CROPS = ("8x10", "5x7")
```

`pipeline/__main__.py`:
```python
import argparse

def cmd_status(args):
    print("photos: (manifest not yet implemented)")
    return 0

def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    ns = ap.parse_args(argv)
    return ns.fn(ns)

if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/process.sh`:
```bash
#!/bin/zsh
exec "$(dirname "$0")/../.venv/bin/python" -m pipeline "$@"
```
Then: `chmod +x scripts/process.sh`

- [ ] **Step 5: Run test to verify it passes, then commit**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v` → PASS.

```bash
git add .gitignore requirements-dev.txt scripts pipeline tests
git commit -m "feat: pipeline scaffolding with CLI entrypoint

Checkpoint 1 findings: <RECORD RT/tool versions and GH7 decode observations here>

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3: Lab profile module + generic-v1

**Files:**
- Create: `pipeline/labprofile.py`, `config/lab-profiles/generic-v1.yaml`, `tests/test_labprofile.py`

**Interfaces:**
- Consumes: `pipeline.paths.CONFIG`.
- Produces: `labprofile.load(name: str) -> dict` (raises `ValueError` on missing/invalid fields); constants `REVIEW_FIELDS = {"safe_edge_percent", "bleed", "color_space", "ppi"}`, `RENDER_FIELDS = {"submission_format", "jpeg_quality", "embed_icc", "max_file_bytes", "filename_rules", "strip_metadata_beyond_allowlist", "keep_capture_date"}`, `ORDER_FIELDS = {"lab_color_correction", "checkout_crop_review"}`; `labprofile.review_view(profile) -> dict` / `labprofile.render_view(profile) -> dict` (sub-dicts used by fingerprint/deps).

- [ ] **Step 1: Write the failing test**

```python
from pipeline import labprofile

def test_load_generic_v1():
    p = labprofile.load("generic-v1")
    assert p["jpeg_quality"] == 92
    assert p["ppi"] == 300
    assert p["safe_edge_percent"] == 2

def test_field_classes_partition():
    all_fields = labprofile.REVIEW_FIELDS | labprofile.RENDER_FIELDS | labprofile.ORDER_FIELDS
    p = labprofile.load("generic-v1")
    assert set(p.keys()) == all_fields

def test_views():
    p = labprofile.load("generic-v1")
    assert set(labprofile.review_view(p)) == labprofile.REVIEW_FIELDS
    assert set(labprofile.render_view(p)) == labprofile.RENDER_FIELDS

def test_missing_field_raises(tmp_repo):
    (tmp_repo / "config/lab-profiles/broken.yaml").write_text("jpeg_quality: 92\n")
    import pytest
    with pytest.raises(ValueError):
        labprofile.load("broken")
```

- [ ] **Step 2: Run to verify FAIL** — `.venv/bin/python -m pytest tests/test_labprofile.py -v` → import error.

- [ ] **Step 3: Implement**

`config/lab-profiles/generic-v1.yaml` — exact values from spec:
```yaml
submission_format: jpeg
jpeg_quality: 92
color_space: srgb
embed_icc: true
ppi: 300
lab_color_correction: "off"
safe_edge_percent: 2
checkout_crop_review: required
max_file_bytes: 26214400
filename_rules: "ASCII, <= 64 chars"
bleed: none
strip_metadata_beyond_allowlist: true
keep_capture_date: true
```

`pipeline/labprofile.py`:
```python
import yaml
from . import paths

REVIEW_FIELDS = {"safe_edge_percent", "bleed", "color_space", "ppi"}
RENDER_FIELDS = {"submission_format", "jpeg_quality", "embed_icc", "max_file_bytes",
                 "filename_rules", "strip_metadata_beyond_allowlist", "keep_capture_date"}
ORDER_FIELDS = {"lab_color_correction", "checkout_crop_review"}

def load(name):
    f = paths.CONFIG / "lab-profiles" / f"{name}.yaml"
    if not f.exists():
        raise ValueError(f"no lab profile {name}")
    p = yaml.safe_load(f.read_text())
    missing = (REVIEW_FIELDS | RENDER_FIELDS | ORDER_FIELDS) - set(p)
    if missing:
        raise ValueError(f"lab profile {name} missing fields: {sorted(missing)}")
    return p

def review_view(p):
    return {k: p[k] for k in sorted(REVIEW_FIELDS)}

def render_view(p):
    return {k: p[k] for k in sorted(RENDER_FIELDS)}
```

Note: `paths.ROOT` reads `PIPELINE_ROOT` at import time; `labprofile` must read `paths.CONFIG` lazily for the tmp_repo test to work. In `load()`, replace `paths.CONFIG` with `paths.ROOT / "config"` computed via a module-level function `_config_dir()` that re-reads `os.environ`, OR simpler: have `paths` expose functions. Decision: change `paths.py` so every path is a function (`paths.root()`, `paths.config()`, etc.) returning fresh Paths; update Task 2's constants accordingly (`INPUT` → `input_dir()` etc.) and keep tuple constants as-is. Apply that refactor in this task and update `tests/test_cli.py` if needed.

- [ ] **Step 4: Run to verify PASS** — full suite: `.venv/bin/python -m pytest -v`.

- [ ] **Step 5: Commit** — `git add pipeline config tests && git commit -m "feat: lab profile module with generic-v1 and field classes ..."` (co-author trailer per Global Constraints).

### Task 4: Geometry module (pure math)

**Files:**
- Create: `pipeline/geometry.py`, `tests/test_geometry.py`

**Interfaces:**
- Produces: `geometry.target_pixels(crop: str, landscape: bool, ppi: int) -> tuple[int, int]`; `geometry.centered_crop(w: int, h: int, crop: str, landscape: bool) -> dict` returning `{"x": int, "y": int, "w": int, "h": int}` in source pixels; `geometry.validate_crop(window: dict, w: int, h: int, crop: str, landscape: bool) -> None` (raises `ValueError` on out-of-bounds, wrong aspect beyond ±0.5 %, or upscale — window smaller than target pixels); `geometry.pdf_page_inches(crop: str | None, w: int, h: int, ppi: int, landscape: bool) -> tuple[float, float]`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pipeline import geometry

def test_target_pixels():
    assert geometry.target_pixels("8x10", landscape=False, ppi=300) == (2400, 3000)
    assert geometry.target_pixels("8x10", landscape=True, ppi=300) == (3000, 2400)
    assert geometry.target_pixels("5x7", landscape=False, ppi=300) == (1500, 2100)
    assert geometry.target_pixels("5x7", landscape=True, ppi=300) == (2100, 1500)

def test_centered_crop_landscape_8x10():
    win = geometry.centered_crop(5776, 4336, "8x10", landscape=True)
    assert win["h"] == 4336          # full height used
    assert win["w"] == 5420          # 4336 * 10/8 = 5420
    assert win["x"] == (5776 - 5420) // 2 and win["y"] == 0

def test_validate_rejects_out_of_bounds():
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 5000, "y": 0, "w": 5420, "h": 4336},
                               5776, 4336, "8x10", landscape=True)

def test_validate_rejects_upscale():
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0, "y": 0, "w": 2000, "h": 1600},
                               5776, 4336, "8x10", landscape=True)

def test_pdf_page_inches():
    assert geometry.pdf_page_inches("8x10", 2400, 3000, 300, landscape=False) == (8.0, 10.0)
    assert geometry.pdf_page_inches(None, 5776, 4336, 300, landscape=True) == (5776/300, 4336/300)
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
SIZES = {"8x10": (8, 10), "5x7": (5, 7)}

def target_pixels(crop, landscape, ppi):
    a, b = SIZES[crop]
    w, h = (b * ppi, a * ppi) if landscape else (a * ppi, b * ppi)
    return (w, h)

def centered_crop(w, h, crop, landscape):
    tw, th = target_pixels(crop, landscape, 300)
    aspect = tw / th
    if w / h > aspect:                 # source wider than crop: full height
        ch = h
        cw = round(h * aspect)
    else:                              # source taller: full width
        cw = w
        ch = round(w / aspect)
    return {"x": (w - cw) // 2, "y": (h - ch) // 2, "w": cw, "h": ch}

def validate_crop(win, w, h, crop, landscape):
    if win["x"] < 0 or win["y"] < 0 or win["x"] + win["w"] > w or win["y"] + win["h"] > h:
        raise ValueError(f"crop window out of bounds: {win}")
    tw, th = target_pixels(crop, landscape, 300)
    if abs((win["w"] / win["h"]) - (tw / th)) / (tw / th) > 0.005:
        raise ValueError(f"crop window aspect mismatch: {win}")
    if win["w"] < tw or win["h"] < th:
        raise ValueError(f"crop window would require upscaling: {win}")

def pdf_page_inches(crop, w, h, ppi, landscape):
    if crop is None:
        return (w / ppi, h / ppi)
    a, b = SIZES[crop]
    return (float(b), float(a)) if landscape else (float(a), float(b))
```

- [ ] **Step 4: Run to verify PASS** (full suite). **Step 5: Commit.**

### Task 5: Toolchain lock

**Files:**
- Create: `pipeline/toolchain.py`, `tests/test_toolchain.py`
- Create (generated, committed): `config/toolchain.lock`

**Interfaces:**
- Produces: `toolchain.discover() -> dict` (entry per tool: `{"path": str, "version": str, "sha256": str}`); `toolchain.write_lock(entries: dict, lock_path: Path)`; `toolchain.verify(lock_path: Path) -> list[str]` (returns list of mismatch descriptions, empty = OK); `toolchain.RENDER_TOOLS = {"rawtherapee"}`, `toolchain.CROP_TOOLS = {"magick"}`, `toolchain.PDF_TOOLS = {"img2pdf"}`, `toolchain.VERIFY_TOOLS = {"qpdf", "pdfimages", "exiftool"}`; `toolchain.entries_for(lock: dict, names: set[str]) -> dict`.
- Consumes: `paths.RT_CLI`.

- [ ] **Step 1: Write the failing test** (pure parts tested with a fake lock; discovery is integration)

```python
import json
from pipeline import toolchain

FAKE = {"rawtherapee": {"path": "/x", "version": "5.12", "sha256": "aa"},
        "magick": {"path": "/y", "version": "7.1", "sha256": "bb"}}

def test_write_and_verify_roundtrip(tmp_path):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    assert json.loads(lock.read_text()) == FAKE

def test_verify_reports_mismatch(tmp_path, monkeypatch):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: {**FAKE,
        "magick": {"path": "/y", "version": "7.2", "sha256": "cc"}})
    problems = toolchain.verify(lock)
    assert problems and "magick" in problems[0]

def test_entries_for_subsets():
    assert set(toolchain.entries_for(FAKE, {"magick"})) == {"magick"}
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
import hashlib, json, shutil, subprocess
from pathlib import Path
from . import paths

RENDER_TOOLS = {"rawtherapee"}
CROP_TOOLS = {"magick"}
PDF_TOOLS = {"img2pdf"}
VERIFY_TOOLS = {"qpdf", "pdfimages", "exiftool"}

_VERSION_ARGS = {"rawtherapee": ["--version"], "magick": ["--version"],
                 "img2pdf": ["--version"], "qpdf": ["--version"],
                 "exiftool": ["-ver"], "pdfimages": ["-v"]}

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _tool_path(name):
    return paths.RT_CLI if name == "rawtherapee" else shutil.which(name)

def discover():
    entries = {}
    for name, args in _VERSION_ARGS.items():
        p = _tool_path(name)
        if not p or not Path(p).exists():
            raise RuntimeError(f"tool not found: {name}")
        out = subprocess.run([p, *args], capture_output=True, text=True)
        version = (out.stdout or out.stderr).strip().splitlines()[0]
        entries[name] = {"path": p, "version": version, "sha256": _sha256(p)}
    return entries

def write_lock(entries, lock_path):
    lock_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n")

def verify(lock_path):
    want = json.loads(Path(lock_path).read_text())
    have = discover()
    problems = []
    for name, entry in want.items():
        h = have.get(name)
        if h is None:
            problems.append(f"{name}: missing")
        elif h["sha256"] != entry["sha256"]:
            problems.append(f"{name}: hash mismatch ({entry['version']} -> {h['version']})")
    return problems

def entries_for(lock, names):
    return {k: lock[k] for k in sorted(names) if k in lock}
```

- [ ] **Step 4: Run to verify PASS**, then generate the real lock (integration):

```bash
.venv/bin/python -c "from pipeline import toolchain, paths; toolchain.write_lock(toolchain.discover(), paths.root()/'config/toolchain.lock'); print('lock written')"
.venv/bin/python -c "from pipeline import toolchain, paths; print(toolchain.verify(paths.root()/'config/toolchain.lock') or 'lock verifies clean')"
```
Expected: `lock written`, then `lock verifies clean`.

- [ ] **Step 5: Commit** (include `config/toolchain.lock`).

### Task 6: Recipe module + approval fingerprint

**Files:**
- Create: `pipeline/recipe.py`, `tests/test_recipe.py`

**Interfaces:**
- Consumes: `labprofile.review_view`, `toolchain.entries_for`.
- Produces: `recipe.load(stem) -> dict` / `recipe.save(stem, data)` (YAML at `recipes/<stem>.yaml`); `recipe.new(stem, raw_sha256) -> dict` with keys: `raw_sha256`, `crops` (dict crop→window dict or None), `overrides` (dict, e.g. `{"denoise": false}`), `sharpen` (dict crop→unsharp string, defaults below), `expression_audit` (list of str), `approval` (`{"fingerprint": str | None, "approved_at": str | None}`); `recipe.fingerprint(stem, rec, style_hashes: dict, seed_hash: str, lock: dict, lab: dict) -> str` (sha256 hex of canonical JSON over: raw_sha256, crops, overrides, sharpen, style_hashes, seed_hash, render-tool lock entries, labprofile.review_view); `recipe.DEFAULT_SHARPEN = {"native": "0x0.8+0.6+0.008", "8x10": "0x1.0+0.8+0.01", "5x7": "0x0.9+0.9+0.01"}`; `recipe.file_hashes(paths_list) -> dict` (name→sha256).

- [ ] **Step 1: Write the failing test**

```python
from pipeline import recipe, toolchain

LOCK = {"rawtherapee": {"path": "/x", "version": "5.12", "sha256": "aa"},
        "magick": {"path": "/y", "version": "7.1", "sha256": "bb"}}
LAB = {"safe_edge_percent": 2, "bleed": "none", "color_space": "srgb", "ppi": 300,
       "jpeg_quality": 92, "submission_format": "jpeg", "embed_icc": True,
       "max_file_bytes": 1, "filename_rules": "x",
       "strip_metadata_beyond_allowlist": True, "keep_capture_date": True,
       "lab_color_correction": "off", "checkout_crop_review": "required"}

def _fp(rec):
    return recipe.fingerprint("P1", rec, {"natural": "s1"}, "seed1", LOCK, LAB)

def test_fingerprint_stable_and_sensitive():
    rec = recipe.new("P1", "rawhash")
    assert _fp(rec) == _fp(rec)                      # deterministic
    rec2 = recipe.new("P1", "rawhash")
    rec2["crops"]["8x10"] = {"x": 1, "y": 0, "w": 100, "h": 80}
    assert _fp(rec) != _fp(rec2)                     # crop change breaks it

def test_fingerprint_ignores_order_fields():
    rec = recipe.new("P1", "rawhash")
    a = _fp(rec)
    lab2 = dict(LAB, lab_color_correction="on")      # order-only field
    b = recipe.fingerprint("P1", rec, {"natural": "s1"}, "seed1", LOCK, lab2)
    assert a == b

def test_fingerprint_sensitive_to_render_tool():
    rec = recipe.new("P1", "rawhash")
    lock2 = {**LOCK, "rawtherapee": {**LOCK["rawtherapee"], "sha256": "zz"}}
    assert _fp(rec) != recipe.fingerprint("P1", rec, {"natural": "s1"}, "seed1", lock2, LAB)

def test_fingerprint_insensitive_to_verify_tool():
    rec = recipe.new("P1", "rawhash")
    lock2 = {**LOCK, "magick": {**LOCK["magick"], "sha256": "zz"}}
    assert _fp(rec) == recipe.fingerprint("P1", rec, {"natural": "s1"}, "seed1", lock2, LAB)

def test_save_load_roundtrip(tmp_repo):
    rec = recipe.new("P1036163", "rawhash")
    recipe.save("P1036163", rec)
    assert recipe.load("P1036163") == rec
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement**

```python
import hashlib, json
import yaml
from . import paths, labprofile, toolchain

DEFAULT_SHARPEN = {"native": "0x0.8+0.6+0.008",
                   "8x10": "0x1.0+0.8+0.01",
                   "5x7": "0x0.9+0.9+0.01"}

def new(stem, raw_sha256):
    return {"raw_sha256": raw_sha256,
            "crops": {"8x10": None, "5x7": None},
            "overrides": {"denoise": False},
            "sharpen": dict(DEFAULT_SHARPEN),
            "expression_audit": [],
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
                "styles": style_hashes,
                "seed": seed_hash,
                "render_tools": toolchain.entries_for(lock, toolchain.RENDER_TOOLS),
                "lab_review": labprofile.review_view(lab)}
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()
```

(`paths.recipes_dir()` per the Task 3 refactor to path functions.)

- [ ] **Step 4: Run full suite → PASS. Step 5: Commit.**

### Task 7: Manifest + state machine + artifact dependencies

**Files:**
- Create: `pipeline/manifest.py`, `tests/test_manifest.py`

**Interfaces:**
- Consumes: `recipe.fingerprint`, `toolchain.entries_for` + tool-class sets, `labprofile.render_view`.
- Produces: `manifest.STATES = ("ingested", "preview_ready", "review_required", "approved", "rendered", "verified")`; `manifest.load() -> dict` / `manifest.save(m)` (JSON at `.manifest`, `{"photos": {stem: {"state": str, "fingerprint": str|None}}}`); `manifest.set_state(m, stem, state)` (raises on unknown state); `manifest.effective_state(m, stem, current_fp) -> str` (returns stored state, downgraded to `"review_required"` iff stored state is approved-or-later and stored `fingerprint != current_fp`); `manifest.artifact_names(stem, landscape_map=None) -> list[str]` (the 22 filenames); `manifest.artifact_deps(stem, artifact: str, rec, style_hashes, seed_hash, lock, lab, crop_geometry) -> dict` (per spec: TIFs ← raw+style+seed+render tools; JPGs add crop window + sharpen + lab render fields + magick entry; PDFs add img2pdf entry + source JPG identity; sheet ← three native JPG identities).

- [ ] **Step 1: Write the failing test**

```python
from pipeline import manifest

def test_artifact_names_count():
    names = manifest.artifact_names("P1")
    assert len(names) == 22
    assert "P1_natural.tif" in names and "P1_bw_5x7.jpg" in names
    assert "P1_filmic_8x10.pdf" in names and "P1_comparison.pdf" in names

def test_state_downgrade_on_fingerprint_change(tmp_repo):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "old"
    assert manifest.effective_state(m, "P1", "old") == "approved"
    assert manifest.effective_state(m, "P1", "new") == "review_required"

def test_early_states_not_downgraded(tmp_repo):
    m = manifest.load()
    manifest.set_state(m, "P1", "preview_ready")
    m["photos"]["P1"]["fingerprint"] = None
    assert manifest.effective_state(m, "P1", "anything") == "preview_ready"

def test_deps_differ_between_tif_and_jpg():
    from pipeline import recipe
    rec = recipe.new("P1", "raw")
    lock = {"rawtherapee": {"sha256": "aa"}, "magick": {"sha256": "bb"},
            "img2pdf": {"sha256": "cc"}}
    lab = {"jpeg_quality": 92, "submission_format": "jpeg", "embed_icc": True,
           "max_file_bytes": 1, "filename_rules": "x",
           "strip_metadata_beyond_allowlist": True, "keep_capture_date": True}
    tif = manifest.artifact_deps("P1", "P1_natural.tif", rec,
                                 {"natural": "s"}, "seed", lock, lab, None)
    jpg = manifest.artifact_deps("P1", "P1_natural_8x10.jpg", rec,
                                 {"natural": "s"}, "seed", lock, lab,
                                 {"x": 0, "y": 0, "w": 10, "h": 8})
    assert "magick" not in str(tif) and "magick" in str(jpg)
    assert tif != jpg
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import json
from . import paths, labprofile, toolchain

STATES = ("ingested", "preview_ready", "review_required", "approved",
          "rendered", "verified")
_APPROVED_OR_LATER = {"approved", "rendered", "verified"}

def load():
    p = paths.manifest_path()
    if p.exists():
        return json.loads(p.read_text())
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
    names += [n.replace(".jpg", ".pdf") for n in names if n.endswith(".jpg")]
    names.append(f"{stem}_comparison.pdf")
    return names

def artifact_deps(stem, artifact, rec, style_hashes, seed_hash, lock, lab, crop_geometry):
    style = next((s for s in paths.STYLES if f"_{s}" in artifact), None)
    base = {"raw": rec["raw_sha256"], "seed": seed_hash,
            "style": style_hashes.get(style),
            "render_tools": toolchain.entries_for(lock, toolchain.RENDER_TOOLS)}
    if artifact.endswith(".tif"):
        return base
    base["lab_render"] = labprofile.render_view(lab)
    base["crop_tools"] = toolchain.entries_for(lock, toolchain.CROP_TOOLS)
    crop = next((c for c in paths.CROPS if artifact.endswith(f"_{c}.jpg") or artifact.endswith(f"_{c}.pdf")), None)
    base["crop"] = crop_geometry if crop else None
    base["sharpen"] = rec["sharpen"][crop or "native"] if style else None
    if artifact.endswith(".pdf"):
        base["pdf_tools"] = toolchain.entries_for(lock, toolchain.PDF_TOOLS)
    if artifact.endswith("_comparison.pdf"):
        base["sources"] = [f"{stem}_{s}.jpg" for s in paths.STYLES]
    return base
```

- [ ] **Step 4: Full suite PASS. Step 5: Commit.**

### Task 8: Ingest — preflight + archive

**Files:**
- Create: `pipeline/ingest.py`, `tests/test_ingest.py`
- Modify: `pipeline/__main__.py` (add `ingest` subcommand)

**Interfaces:**
- Consumes: `recipe.new/save`, `manifest.load/save/set_state`.
- Produces: `ingest.exif_summary(path) -> dict` (via `exiftool -j`: keys `Make, Model, ImageWidth, ImageHeight, Orientation, LensModel, ISO, ExposureTime`); `ingest.preflight(path, existing_stems: set, existing_hashes: set) -> list[str]` (warnings list; raises `IngestError` on duplicate stem/content or unreadable metadata; unexpected Make/Model is a warning, not an error); `ingest.archive(path) -> str` (copies to `archive/`, re-hashes destination, compares to source, returns sha256; raises on mismatch); `ingest.run() -> dict` (per-file result: `ok|failed`, isolates failures per photo).

- [ ] **Step 1: Write the failing test** (pure parts with monkeypatched exif; archive with real temp files)

```python
import pytest
from pipeline import ingest

GOOD = {"Make": "Panasonic", "Model": "DC-GH7", "ImageWidth": 5776,
        "ImageHeight": 4336, "Orientation": "Horizontal (normal)",
        "LensModel": "X", "ISO": 200, "ExposureTime": "1/800"}

def test_preflight_clean(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD))
    assert ingest.preflight("Input/P9.rw2", set(), set()) == []

def test_preflight_flags_high_iso(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD, ISO=3200))
    warns = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("ISO" in w for w in warns)

def test_preflight_flags_unexpected_body(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD, Model="DC-S5"))
    warns = ingest.preflight("Input/P9.rw2", set(), set())
    assert any("DC-S5" in w for w in warns)

def test_preflight_rejects_duplicate_stem(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD))
    with pytest.raises(ingest.IngestError):
        ingest.preflight("Input/P9.rw2", {"P9"}, set())

def test_archive_verifies_hash(tmp_repo):
    src = tmp_repo / "Input/P9.rw2"
    src.write_bytes(b"raw-bytes")
    sha = ingest.archive(src)
    assert (tmp_repo / "archive/P9.rw2").read_bytes() == b"raw-bytes"
    import hashlib
    assert sha == hashlib.sha256(b"raw-bytes").hexdigest()
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import hashlib, json, shutil, subprocess
from pathlib import Path
from . import paths, recipe, manifest

class IngestError(Exception):
    pass

EXPECTED = {"Make": "Panasonic", "Model": "DC-GH7"}
_KEYS = ["Make", "Model", "ImageWidth", "ImageHeight", "Orientation",
         "LensModel", "ISO", "ExposureTime"]

def exif_summary(path):
    out = subprocess.run(["exiftool", "-j", *[f"-{k}" for k in _KEYS], str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)[0]

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def preflight(path, existing_stems, existing_hashes):
    stem = Path(path).stem
    if stem in existing_stems:
        raise IngestError(f"duplicate stem {stem}: needs explicit user confirmation")
    meta = exif_summary(path)
    if not meta.get("ImageWidth") or not meta.get("ImageHeight"):
        raise IngestError(f"{stem}: unreadable dimensions")
    warns = []
    for k, v in EXPECTED.items():
        if meta.get(k) != v:
            warns.append(f"{stem}: unexpected {k} {meta.get(k)!r} (expected {v!r})")
    if isinstance(meta.get("ISO"), int) and meta["ISO"] > 1600:
        warns.append(f"{stem}: high ISO {meta['ISO']} — consider per-image denoise override")
    return warns

def archive(path):
    path = Path(path)
    src_sha = _sha256(path)
    if src_sha in _archived_hashes():
        raise IngestError(f"{path.name}: identical content already archived")
    dest = paths.archive_dir() / path.name
    shutil.copy2(path, dest)
    if _sha256(dest) != src_sha:
        dest.unlink()
        raise IngestError(f"{path.name}: archive copy hash mismatch")
    with open(paths.archive_dir() / "SHA256SUMS", "a") as f:
        f.write(f"{src_sha}  {path.name}\n")
    return src_sha

def _archived_hashes():
    sums = paths.archive_dir() / "SHA256SUMS"
    if not sums.exists():
        return set()
    return {line.split()[0] for line in sums.read_text().splitlines() if line.strip()}

def run():
    m = manifest.load()
    results = {}
    for raw in sorted(paths.input_dir().glob("*.rw2")):
        stem = raw.stem
        if stem in m["photos"]:
            results[stem] = "skipped (already ingested)"
            continue
        try:
            warns = preflight(raw, set(m["photos"]), _archived_hashes())
            for w in warns:
                print(f"WARNING: {w}")
            sha = archive(raw)
            recipe.save(stem, recipe.new(stem, sha))
            manifest.set_state(m, stem, "ingested")
            results[stem] = "ok"
        except IngestError as e:
            results[stem] = f"failed: {e}"
            print(f"FAILED {stem}: {e}")
    manifest.save(m)
    return results
```

Wire `ingest` into `__main__.py`:
```python
def cmd_ingest(args):
    from . import ingest as ing
    results = ing.run()
    for stem, r in sorted(results.items()):
        print(f"{stem}: {r}")
    return 0 if all("failed" not in r for r in results.values()) else 1
```

- [ ] **Step 4: Full suite PASS. Then integration on the real files:**

Run: `scripts/process.sh ingest`
Expected: `P1036163: ok`, `P1036170: ok`; `archive/` contains both RW2s + `SHA256SUMS`; `recipes/P1036163.yaml` and `recipes/P1036170.yaml` exist.

- [ ] **Step 5: Commit** (recipes are committed; archive is gitignored).

### Task 9: Base styles + RawTherapee render wrapper + previews

**Files:**
- Create: `config/styles/natural.pp3`, `config/styles/filmic.pp3`, `config/styles/bw.pp3`, `config/rawtherapee-seed/options`, `pipeline/render.py`, `tests/test_render.py`
- Modify: `pipeline/__main__.py` (add `preview` subcommand)

**Interfaces:**
- Consumes: `paths.RT_CLI`, recipes/sidecars.
- Produces: `render.rt_render(raw: Path, style: str, out_path: Path, fmt: str, quality: int | None) -> None` (fmt `"tif16"` or `"jpg"`; builds `-p config/styles/<style>.pp3` + `-p sidecars/<stem>_<style>.pp3` if it exists; isolated `XDG_CONFIG_HOME`; raises `RenderError` on nonzero exit or missing output); `render.preview(stem, style) -> Path` (JPG into `previews/`); `render.ensure_sidecar(stem, style) -> Path` (creates empty commented override pp3 if absent); `render.style_hashes() -> dict` (style → sha256 over base pp3 + sidecar, per stem: `render.style_hashes(stem)`); `render.seed_hash() -> str`.

- [ ] **Step 1: Write base style profiles.** These are starting points; the review loop tunes per image via sidecars. RawTherapee `.pp3` partial profiles — unspecified sections stay at RT neutral defaults.

`config/styles/natural.pp3`:
```ini
[Version]
AppVersion=5.12
Version=351

[White Balance]
Setting=Camera

[Exposure]
Auto=false
Compensation=0
HistogramMatching=true

[Color appearance]
Enabled=false

[Vibrance]
Enabled=true
Pastels=12
Saturated=6
ProtectSkins=true
AvoidColorShift=true

[HLRecovery]
Enabled=true
Method=Coloropp

[Sharpening]
Enabled=true
Method=usm
Radius=0.6
Amount=120
Threshold=20;80;2000;1200;

[LensProfile]
LcMode=lcp
UseDistortion=true
UseVignette=true
UseCA=true

[Color Management]
OutputProfile=RTv4_sRGB
```

`config/styles/filmic.pp3` — natural plus a gentle warm shift and soft curve (full copy of natural.pp3 with these sections changed/added):
```ini
[White Balance]
Setting=Custom
Temperature=5650
Green=1.0

[Exposure]
Auto=false
Compensation=0
HistogramMatching=true
CurveMode=Standard
Curve=1;0;0;0.12;0.09;0.50;0.52;0.88;0.92;1;1;
```

`config/styles/bw.pp3` — natural plus:
```ini
[Black & White]
Enabled=true
Method=Desaturation
Setting=RGB-Rel
MixerRed=28
MixerGreen=52
MixerBlue=20
```

`config/rawtherapee-seed/options`: create empty file with comment header `# immutable RT options seed — copied to run/ at render time`. (RT fills defaults for anything unspecified; the seed exists so GUI settings can never leak in.)

- [ ] **Step 2: Write the failing test** (command construction, monkeypatched subprocess)

```python
from pathlib import Path
from pipeline import render

def test_rt_command_layers_profiles(tmp_repo, monkeypatch):
    (tmp_repo / "config/styles/natural.pp3").write_text("[Version]\n")
    (tmp_repo / "sidecars/P1_natural.pp3").write_text("[Exposure]\n")
    (tmp_repo / "Input/P1.rw2").write_bytes(b"x")
    calls = {}
    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        calls["env"] = kw.get("env")
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"out")
        class R: returncode = 0; stderr = ""
        return R()
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    render.rt_render(tmp_repo / "Input/P1.rw2", "natural",
                     tmp_repo / "staging/P1_natural.tif", "tif16", None)
    cmd = calls["cmd"]
    p_indices = [i for i, a in enumerate(cmd) if a == "-p"]
    assert len(p_indices) == 2                      # base then sidecar
    assert "natural.pp3" in cmd[p_indices[0] + 1]
    assert "P1_natural.pp3" in cmd[p_indices[1] + 1]
    assert "-b16" in cmd and "-tz" in cmd and "-d" not in cmd
    assert "XDG_CONFIG_HOME" in calls["env"]

def test_ensure_sidecar_creates_once(tmp_repo):
    p = render.ensure_sidecar("P1", "natural")
    assert p.exists()
    first = p.read_text()
    assert render.ensure_sidecar("P1", "natural").read_text() == first
```

- [ ] **Step 3: FAIL, then implement**

```python
import hashlib, os, shutil, subprocess, uuid
from pathlib import Path
from . import paths

class RenderError(Exception):
    pass

def _isolated_env():
    run_dir = paths.run_dir() / f"rt-{uuid.uuid4().hex[:8]}"
    rt_cfg = run_dir / "RawTherapee"
    rt_cfg.mkdir(parents=True)
    seed = paths.config_dir() / "rawtherapee-seed" / "options"
    if seed.exists():
        shutil.copy2(seed, rt_cfg / "options")
    env = dict(os.environ, XDG_CONFIG_HOME=str(run_dir), XDG_CACHE_HOME=str(run_dir / "cache"))
    return env

def rt_render(raw, style, out_path, fmt, quality):
    base = paths.config_dir() / "styles" / f"{style}.pp3"
    sidecar = paths.sidecars_dir() / f"{Path(raw).stem}_{style}.pp3"
    cmd = [paths.RT_CLI, "-o", str(out_path), "-Y", "-q"]
    if fmt == "tif16":
        cmd += ["-b16", "-tz"]
    elif fmt == "jpg":
        cmd += [f"-j{quality or 92}", "-js3"]
    cmd += ["-p", str(base)]
    if sidecar.exists():
        cmd += ["-p", str(sidecar)]
    cmd += ["-c", str(raw)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True, env=_isolated_env())
    if r.returncode != 0 or not Path(out_path).exists():
        raise RenderError(f"rawtherapee failed for {raw} [{style}]: {r.stderr[-500:]}")

def ensure_sidecar(stem, style):
    p = paths.sidecars_dir() / f"{stem}_{style}.pp3"
    if not p.exists():
        p.write_text(f"# per-image override for {stem} [{style}] — layered over "
                     f"config/styles/{style}.pp3\n")
    return p

def preview(stem, style):
    raw = paths.input_dir() / f"{stem}.rw2"
    out = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
    rt_render(raw, style, out, "jpg", 92)
    return out

def _h(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def style_hashes(stem):
    out = {}
    for s in paths.STYLES:
        parts = _h(paths.config_dir() / "styles" / f"{s}.pp3")
        sc = paths.sidecars_dir() / f"{stem}_{s}.pp3"
        if sc.exists():
            parts += _h(sc)
        out[s] = hashlib.sha256(parts.encode()).hexdigest()
    return out

def seed_hash():
    seed = paths.config_dir() / "rawtherapee-seed" / "options"
    return _h(seed) if seed.exists() else "no-seed"
```

Wire `preview` subcommand: `scripts/process.sh preview P1036163 natural` → prints preview path.

- [ ] **Step 4: Unit tests PASS, then integration:**

```bash
scripts/process.sh preview P1036163 natural
```
Expected: exit 0, preview JPG created. **Read the preview JPG** and confirm it renders a plausible natural image. Repeat for `filmic` and `bw` (filmic slightly warmer; bw monochrome). If `-js3` or a pp3 key is rejected by this RT version (check stderr), consult `rawtherapee-cli` help output and adjust the flag/key, rerun, and note the change in the commit message.

- [ ] **Step 5: Commit** (styles, seed, render.py, sidecars created so far).

### Task 10: Crops, resample, output sharpen, JPG export (ImageMagick)

**Files:**
- Create: `pipeline/crops.py`, `tests/test_crops.py`

**Interfaces:**
- Consumes: `geometry.*`, recipe sharpen strings.
- Produces: `crops.jpg_from_tif(tif: Path, out_jpg: Path, crop_window: dict | None, target: tuple[int,int] | None, unsharp: str, quality: int, ppi: int) -> None` — builds and runs one `magick` command: optional `-crop WxH+X+Y +repage`, optional `-filter Lanczos -resize WxH!`, always `-unsharp <str> -quality <q> -density <ppi> -units PixelsPerInch`; raises `CropError` on failure. `crops.magick_cmd(...) -> list[str]` (pure builder, unit-tested separately from execution).

- [ ] **Step 1: Write the failing test**

```python
from pipeline import crops

def test_magick_cmd_native():
    cmd = crops.magick_cmd("in.tif", "out.jpg", None, None, "0x0.8+0.6+0.008", 92, 300)
    assert "-crop" not in cmd and "-resize" not in cmd
    assert "-unsharp" in cmd and "92" in cmd

def test_magick_cmd_crop_and_resize():
    cmd = crops.magick_cmd("in.tif", "out.jpg", {"x": 178, "y": 0, "w": 5420, "h": 4336},
                           (3000, 2400), "0x1.0+0.8+0.01", 92, 300)
    i = cmd.index("-crop")
    assert cmd[i + 1] == "5420x4336+178+0"
    assert cmd[cmd.index("-resize") + 1] == "3000x2400!"
    assert cmd.index("-crop") < cmd.index("-resize") < cmd.index("-unsharp")
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import subprocess

class CropError(Exception):
    pass

def magick_cmd(tif, out_jpg, crop_window, target, unsharp, quality, ppi):
    cmd = ["magick", str(tif)]
    if crop_window:
        w = crop_window
        cmd += ["-crop", f"{w['w']}x{w['h']}+{w['x']}+{w['y']}", "+repage"]
    if target:
        cmd += ["-filter", "Lanczos", "-resize", f"{target[0]}x{target[1]}!"]
    cmd += ["-unsharp", unsharp, "-quality", str(quality),
            "-density", str(ppi), "-units", "PixelsPerInch", str(out_jpg)]
    return cmd

def jpg_from_tif(tif, out_jpg, crop_window, target, unsharp, quality, ppi):
    r = subprocess.run(magick_cmd(tif, out_jpg, crop_window, target, unsharp, quality, ppi),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise CropError(f"magick failed: {r.stderr[-500:]}")
```

- [ ] **Step 4: Unit PASS + integration:** render one TIF master if not present (`render.rt_render` on P1036163 natural → `staging/P1036163.tmp/P1036163_natural.tif`), then:

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
from pipeline import crops, geometry, render, paths
tif = paths.staging_dir() / "P1036163.tmp" / "P1036163_natural.tif"
if not tif.exists():
    render.rt_render(paths.input_dir()/"P1036163.rw2", "natural", tif, "tif16", None)
import subprocess, json
ident = subprocess.run(["magick", "identify", "-format", "%w %h", str(tif)],
                       capture_output=True, text=True).stdout.split()
w, h = int(ident[0]), int(ident[1])
landscape = w >= h
win = geometry.centered_crop(w, h, "8x10", landscape)
target = geometry.target_pixels("8x10", landscape, 300)
out = paths.previews_dir() / "crop_test_8x10.jpg"
crops.jpg_from_tif(tif, out, win, target, "0x1.0+0.8+0.01", 92, 300)
print(subprocess.run(["magick", "identify", str(out)], capture_output=True, text=True).stdout)
EOF
```
Expected: identify reports exactly 3000x2400 (landscape) or 2400x3000. **Read** `previews/crop_test_8x10.jpg` — confirm no clipped heads and correct framing.

- [ ] **Step 5: Commit.**

### Task 11: Metadata strip + allowlist assertion

**Files:**
- Create: `pipeline/metadata.py`, `tests/test_metadata.py`

**Interfaces:**
- Produces: `metadata.ALLOWED = {"Orientation", "ExposureTime", "FNumber", "ISO", "FocalLength", "LensModel", "DateTimeOriginal", "Copyright", "XResolution", "YResolution", "ResolutionUnit"}`; `metadata.strip(path, keep_capture_date: bool) -> None` (exiftool: remove all, restore allowlist, preserve ICC); `metadata.assert_clean(path, keep_capture_date: bool) -> list[str]` (violations in descriptive namespaces EXIF/XMP/IPTC/MakerNotes; empty = clean); `metadata.DESCRIPTIVE_GROUPS = {"EXIF", "XMP", "IPTC", "MakerNotes"}`.

- [ ] **Step 1: Write the failing test** (integration-style, real exiftool, tiny generated JPG)

```python
import subprocess
from pipeline import metadata

def _make_jpg(tmp_path):
    p = tmp_path / "t.jpg"
    subprocess.run(["magick", "-size", "32x32", "xc:gray", str(p)], check=True)
    subprocess.run(["exiftool", "-overwrite_original", "-GPSLatitude=1.5",
                    "-GPSLatitudeRef=N", "-Artist=Somebody", "-ISO=200",
                    "-SerialNumber=ABC123", str(p)], check=True)
    return p

def test_strip_removes_private_keeps_allowed(tmp_path):
    p = _make_jpg(tmp_path)
    metadata.strip(p, keep_capture_date=True)
    out = subprocess.run(["exiftool", "-j", "-G0", str(p)],
                         capture_output=True, text=True).stdout
    assert "GPS" not in out and "Somebody" not in out and "ABC123" not in out
    assert metadata.assert_clean(p, keep_capture_date=True) == []

def test_assert_flags_leftover_gps(tmp_path):
    p = _make_jpg(tmp_path)
    violations = metadata.assert_clean(p, keep_capture_date=True)
    assert any("GPS" in v for v in violations)
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import json, subprocess

DESCRIPTIVE_GROUPS = {"EXIF", "XMP", "IPTC", "MakerNotes"}
ALLOWED = {"Orientation", "ExposureTime", "FNumber", "ISO", "FocalLength",
           "LensModel", "DateTimeOriginal", "Copyright",
           "XResolution", "YResolution", "ResolutionUnit"}

def strip(path, keep_capture_date):
    keep = ALLOWED - ({"DateTimeOriginal"} if not keep_capture_date else set())
    cmd = ["exiftool", "-overwrite_original", "-all=", "--icc_profile:all",
           "-tagsfromfile", "@"] + [f"-EXIF:{t}" for t in sorted(keep)] + [str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"exiftool strip failed: {r.stderr[-300:]}")

def assert_clean(path, keep_capture_date):
    out = subprocess.run(["exiftool", "-j", "-G0", "-s", str(path)],
                         capture_output=True, text=True, check=True).stdout
    tags = json.loads(out)[0]
    allowed = ALLOWED - ({"DateTimeOriginal"} if not keep_capture_date else set())
    violations = []
    for key, val in tags.items():
        if ":" not in key:
            continue
        group, name = key.split(":", 1)
        if group in DESCRIPTIVE_GROUPS and name not in allowed:
            violations.append(f"{key}={val!r}")
    return violations
```

Note: exiftool JSON keys with `-G0 -s` look like `"EXIF:GPSLatitude"`. If the running exiftool emits them without the group prefix, switch to parsing `exiftool -G0 -s -s` line output instead — adjust while keeping the same return contract.

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 12: PDFs — img2pdf wraps + comparison sheet

**Files:**
- Create: `pipeline/pdfs.py`, `tests/test_pdfs.py`

**Interfaces:**
- Consumes: `geometry.pdf_page_inches`.
- Produces: `pdfs.wrap(jpg: Path, out_pdf: Path, page_inches: tuple[float, float]) -> None` (img2pdf, exact page box, no re-encode); `pdfs.comparison_sheet(stem, native_jpgs: dict[str, Path], staging_dir: Path) -> Path` (magick montage of the three labeled panels → `<stem>_comparison_src.jpg` at 3300×2550 300 PPI → img2pdf Letter → `<stem>_comparison.pdf`; the intermediate composite JPG stays in staging as the losslessness-proof source).

- [ ] **Step 1: Write the failing test**

```python
import subprocess
from pipeline import pdfs

def _jpg(tmp_path, name):
    p = tmp_path / name
    subprocess.run(["magick", "-size", "300x400", "xc:gray", "-density", "300",
                    "-units", "PixelsPerInch", str(p)], check=True)
    return p

def test_wrap_page_box(tmp_path):
    jpg = _jpg(tmp_path, "a.jpg")
    pdf = tmp_path / "a.pdf"
    pdfs.wrap(jpg, pdf, (8.0, 10.0))
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    # 8in x 10in = 576 x 720 pts
    assert "576 x 720" in info

def test_wrap_is_lossless(tmp_path):
    import hashlib
    jpg = _jpg(tmp_path, "b.jpg")
    pdf = tmp_path / "b.pdf"
    pdfs.wrap(jpg, pdf, (8.0, 10.0))
    subprocess.run(["pdfimages", "-j", str(pdf), str(tmp_path / "ex")], check=True)
    extracted = next(tmp_path.glob("ex-*.jpg"))
    assert hashlib.sha256(extracted.read_bytes()).hexdigest() == \
           hashlib.sha256(jpg.read_bytes()).hexdigest()

def test_comparison_sheet(tmp_path):
    jpgs = {s: _jpg(tmp_path, f"{s}.jpg") for s in ("natural", "filmic", "bw")}
    out = pdfs.comparison_sheet("P1", jpgs, tmp_path)
    assert out.name == "P1_comparison.pdf" and out.exists()
    assert (tmp_path / "P1_comparison_src.jpg").exists()
    info = subprocess.run(["pdfinfo", str(out)], capture_output=True, text=True).stdout
    assert "792 x 612" in info          # landscape US Letter in pts
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import subprocess
from pathlib import Path

class PdfError(Exception):
    pass

def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise PdfError(f"{cmd[0]} failed: {r.stderr[-400:]}")

def wrap(jpg, out_pdf, page_inches):
    w, h = page_inches
    _run(["img2pdf", str(jpg), "--pagesize", f"{w}inx{h}in", "-o", str(out_pdf)])

def comparison_sheet(stem, native_jpgs, staging_dir):
    src = Path(staging_dir) / f"{stem}_comparison_src.jpg"
    _run(["magick", "montage",
          "-label", "natural", str(native_jpgs["natural"]),
          "-label", "filmic", str(native_jpgs["filmic"]),
          "-label", "bw", str(native_jpgs["bw"]),
          "-tile", "3x1", "-geometry", "+20+20", "-background", "white",
          "-density", "300", "-units", "PixelsPerInch",
          "-resize", "3300x2550", "-gravity", "center",
          "-extent", "3300x2550", "-quality", "92", str(src)])
    out = Path(staging_dir) / f"{stem}_comparison.pdf"
    wrap(src, out, (11.0, 8.5))    # landscape US Letter: 792 x 612 pts
    return out
```

The sheet is landscape Letter (three side-by-side panels): composite is
3300×2550 px (11 × 8.5 in at 300 PPI), so `pdfinfo` reports `792 x 612 pts` —
the test's expected string is `"792 x 612"`. After the test passes, **Read**
the composite JPG and confirm the three panels are labeled and sensibly laid
out.

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 13: Verify — QA suite

**Files:**
- Create: `pipeline/verify.py`, `tests/test_verify.py`

**Interfaces:**
- Consumes: `geometry`, `metadata.assert_clean`, lab profile.
- Produces: `verify.check_image(path, expect_w, expect_h, expect_bits, ppi, max_bytes) -> list[str]` (magick identify + exiftool: exact dimensions, bit depth, RGB/Gray-in-RGB mode, sRGB ICC present, DPI tags, nonzero and ≤ max bytes); `verify.check_pdf(pdf, source_jpg, page_pts: tuple[int,int], workdir) -> list[str]` (`qpdf --check` exits 0; `pdfimages -list` shows exactly one jpeg image; `pdfimages -j` extraction SHA-256 equals source; `pdfinfo` page size equals expected pts); `verify.photo(stem, staging_photo_dir, rec, lab, landscape) -> list[str]` (runs every check for all 22 artifacts + metadata assertions; empty = pass).

- [ ] **Step 1: Write the failing test** (drive `check_image`/`check_pdf` with small generated fixtures, same technique as Tasks 11–12: a 300×400 gray JPG must pass `check_image(300, 400, 8, ...)` and fail with wrong expected dims; a wrapped PDF must pass `check_pdf` and fail when compared against a different source JPG. Write four tests: `test_image_pass`, `test_image_wrong_dims`, `test_pdf_pass`, `test_pdf_wrong_source`.)

```python
import subprocess
from pipeline import verify, pdfs

def _jpg(tmp_path, name="v.jpg"):
    p = tmp_path / name
    subprocess.run(["magick", "-size", "300x400", "xc:gray", "-density", "300",
                    "-units", "PixelsPerInch", str(p)], check=True)
    return p

def test_image_pass(tmp_path):
    assert verify.check_image(_jpg(tmp_path), 300, 400, 8, 300, 10_000_000) == []

def test_image_wrong_dims(tmp_path):
    probs = verify.check_image(_jpg(tmp_path), 999, 400, 8, 300, 10_000_000)
    assert any("dimensions" in p for p in probs)

def test_pdf_pass(tmp_path):
    jpg = _jpg(tmp_path)
    pdf = tmp_path / "v.pdf"
    pdfs.wrap(jpg, pdf, (1.0, 400/300))
    assert verify.check_pdf(pdf, jpg, (72, 96), tmp_path) == []

def test_pdf_wrong_source(tmp_path):
    jpg = _jpg(tmp_path)
    other = _jpg(tmp_path, "other.jpg")
    subprocess.run(["exiftool", "-overwrite_original", "-Comment=x", str(other)], check=True)
    pdf = tmp_path / "v.pdf"
    pdfs.wrap(jpg, pdf, (1.0, 400/300))
    assert any("sha256" in p.lower() for p in verify.check_pdf(pdf, other, (72, 96), tmp_path))
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import hashlib, json, re, subprocess
from pathlib import Path
from . import metadata

def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def check_image(path, expect_w, expect_h, expect_bits, ppi, max_bytes):
    problems = []
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return [f"{path.name}: missing or empty"]
    if path.stat().st_size > max_bytes:
        problems.append(f"{path.name}: {path.stat().st_size} bytes exceeds max {max_bytes}")
    out = subprocess.run(["magick", "identify", "-format", "%w %h %z %[colorspace]", str(path)],
                         capture_output=True, text=True).stdout.split()
    w, h, bits, cs = int(out[0]), int(out[1]), int(out[2]), out[3]
    if (w, h) != (expect_w, expect_h):
        problems.append(f"{path.name}: dimensions {w}x{h}, expected {expect_w}x{expect_h}")
    if bits != expect_bits:
        problems.append(f"{path.name}: bit depth {bits}, expected {expect_bits}")
    if cs not in ("sRGB", "Gray", "RGB"):
        problems.append(f"{path.name}: colorspace {cs}")
    meta = json.loads(subprocess.run(
        ["exiftool", "-j", "-ICC_Profile:ProfileDescription", "-XResolution", str(path)],
        capture_output=True, text=True).stdout)[0]
    if "sRGB" not in str(meta.get("ProfileDescription", "")):
        problems.append(f"{path.name}: missing/non-sRGB ICC profile")
    if path.suffix == ".jpg" and int(float(meta.get("XResolution", 0))) != ppi:
        problems.append(f"{path.name}: XResolution {meta.get('XResolution')}, expected {ppi}")
    return problems

def check_pdf(pdf, source_jpg, page_pts, workdir):
    problems = []
    if subprocess.run(["qpdf", "--check", str(pdf)], capture_output=True).returncode != 0:
        problems.append(f"{Path(pdf).name}: qpdf --check failed")
    listing = subprocess.run(["pdfimages", "-list", str(pdf)],
                             capture_output=True, text=True).stdout
    data_rows = [l for l in listing.splitlines()[2:] if l.strip()]
    if len(data_rows) != 1 or " jpeg " not in f" {data_rows[0]} ":
        problems.append(f"{Path(pdf).name}: expected exactly one embedded jpeg, got: {listing!r}")
    prefix = Path(workdir) / f"extract_{Path(pdf).stem}"
    subprocess.run(["pdfimages", "-j", str(pdf), str(prefix)], capture_output=True)
    extracted = sorted(Path(workdir).glob(f"extract_{Path(pdf).stem}-*.jpg"))
    if not extracted or _sha(extracted[0]) != _sha(source_jpg):
        problems.append(f"{Path(pdf).name}: embedded JPEG sha256 mismatch vs source")
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    m = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts", info)
    if not m or (round(float(m.group(1))), round(float(m.group(2)))) != page_pts:
        problems.append(f"{Path(pdf).name}: page size {m and m.groups()}, expected {page_pts} pts")
    return problems
```

`verify.photo(...)` — include this in the same file:

```python
def photo(stem, staging_dir, rec, lab, landscape):
    from . import geometry, manifest, metadata as md
    staging_dir = Path(staging_dir)
    problems = []
    ppi, maxb, q = lab["ppi"], lab["max_file_bytes"], lab["jpeg_quality"]
    # native dims come from the natural TIF master
    out = subprocess.run(["magick", "identify", "-format", "%w %h",
                          str(staging_dir / f"{stem}_natural.tif")],
                         capture_output=True, text=True).stdout.split()
    nw, nh = int(out[0]), int(out[1])
    landscape = nw >= nh
    for name in manifest.artifact_names(stem):
        p = staging_dir / name
        crop = next((c for c in ("8x10", "5x7") if f"_{c}." in name), None)
        if name.endswith(".tif"):
            problems += check_image(p, nw, nh, 16, ppi, maxb)
        elif name.endswith(".jpg"):
            w, h = (geometry.target_pixels(crop, landscape, ppi) if crop else (nw, nh))
            problems += check_image(p, w, h, 8, ppi, maxb)
            problems += [f"{name}: metadata {v}" for v in
                         md.assert_clean(p, lab["keep_capture_date"])]
        elif name.endswith("_comparison.pdf"):
            src = staging_dir / f"{stem}_comparison_src.jpg"
            problems += check_pdf(p, src, (792, 612), staging_dir)
        elif name.endswith(".pdf"):
            src = staging_dir / name.replace(".pdf", ".jpg")
            w, h = (geometry.target_pixels(crop, landscape, ppi) if crop else (nw, nh))
            iw, ih = geometry.pdf_page_inches(crop, w, h, ppi, landscape)
            problems += check_pdf(p, src, (round(iw * 72), round(ih * 72)), staging_dir)
    return problems
```

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 14: Publish — lockfile, vNNN, current swap, views, recovery, provenance

**Files:**
- Create: `pipeline/publish.py`, `tests/test_publish.py`

**Interfaces:**
- Consumes: `manifest`, staging dirs from `render`.
- Produces: `publish.acquire_lock() -> contextmanager` (O_CREAT|O_EXCL on `run/driver.lock` with pid inside; raises `LockError` if held; removes on exit); `publish.publish(stem, staging_photo_dir: Path, provenance: dict) -> Path` (writes `provenance.json` into staging dir; allocates next `vNNN` via exclusive `mkdir` retry; `os.rename` staging→vNNN; atomic `current` swap via temp symlink + `os.replace`; prunes older vNNN dirs after successful swap); `publish.rebuild_views() -> None` (wipes `Output/TIF|JPG|PDF` and recreates relative symlinks through every `photos/<stem>/current/`); `publish.recover() -> list[str]` (removes orphan `staging/*.tmp`, prunes unreferenced vNNN dirs, reports actions).

- [ ] **Step 1: Write the failing test**

```python
import os
import pytest
from pipeline import publish

def _stage(tmp_repo, stem="P1", files=("P1_natural.tif", "P1_natural.jpg")):
    d = tmp_repo / "staging" / f"{stem}.tmp"
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        (d / f).write_bytes(b"data")
    return d

def test_publish_creates_v001_and_current(tmp_repo):
    d = _stage(tmp_repo)
    publish.publish("P1", d, {"tools": {}})
    photo = tmp_repo / "Output/photos/P1"
    assert (photo / "v001/P1_natural.tif").exists()
    assert (photo / "v001/provenance.json").exists()
    assert os.readlink(photo / "current") == "v001"
    assert not d.exists()

def test_republish_swaps_and_prunes(tmp_repo):
    publish.publish("P1", _stage(tmp_repo), {})
    publish.publish("P1", _stage(tmp_repo), {})
    photo = tmp_repo / "Output/photos/P1"
    assert os.readlink(photo / "current") == "v002"
    assert not (photo / "v001").exists()

def test_lock_excludes_second_holder(tmp_repo):
    with publish.acquire_lock():
        with pytest.raises(publish.LockError):
            with publish.acquire_lock():
                pass

def test_rebuild_views(tmp_repo):
    publish.publish("P1", _stage(tmp_repo), {})
    publish.rebuild_views()
    link = tmp_repo / "Output/JPG/P1_natural.jpg"
    assert link.is_symlink() and link.resolve().read_bytes() == b"data"

def test_recover_removes_orphan_staging(tmp_repo):
    d = _stage(tmp_repo, "P9")
    actions = publish.recover()
    assert not d.exists() and any("P9" in a for a in actions)
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
import json, os, shutil
from contextlib import contextmanager
from pathlib import Path
from . import paths

class LockError(Exception):
    pass

@contextmanager
def acquire_lock():
    paths.run_dir().mkdir(exist_ok=True)
    lock = paths.run_dir() / "driver.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise LockError(f"another driver instance holds {lock}")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)

def _photo_dir(stem):
    return paths.output_dir() / "photos" / stem

def publish(stem, staging_photo_dir, provenance):
    staging_photo_dir = Path(staging_photo_dir)
    (staging_photo_dir / "provenance.json").write_text(json.dumps(provenance, indent=2))
    photo = _photo_dir(stem)
    photo.mkdir(parents=True, exist_ok=True)
    n = 1
    while True:
        vdir = photo / f"v{n:03d}"
        try:
            vdir.mkdir()          # atomic, exclusive allocation
            vdir.rmdir()
            break
        except FileExistsError:
            n += 1
    os.rename(staging_photo_dir, vdir)
    tmp_link = photo / f".current.tmp{os.getpid()}"
    if tmp_link.is_symlink():
        tmp_link.unlink()
    os.symlink(vdir.name, tmp_link)
    os.replace(tmp_link, photo / "current")
    for old in sorted(photo.glob("v[0-9][0-9][0-9]")):
        if old.name != vdir.name:
            shutil.rmtree(old)
    return vdir

def rebuild_views():
    for fmt, exts in (("TIF", (".tif",)), ("JPG", (".jpg",)), ("PDF", (".pdf",))):
        d = paths.output_dir() / fmt
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for photo in sorted((paths.output_dir() / "photos").glob("*")):
            cur = photo / "current"
            if not cur.is_symlink():
                continue
            for f in sorted(cur.glob("*")):
                if f.suffix in exts:
                    os.symlink(os.path.relpath(f.resolve(), d), d / f.name)

def recover():
    actions = []
    for orphan in sorted(paths.staging_dir().glob("*.tmp")):
        shutil.rmtree(orphan)
        actions.append(f"removed orphan staging {orphan.name}")
    for photo in sorted((paths.output_dir() / "photos").glob("*")):
        cur = photo / "current"
        current_target = os.readlink(cur) if cur.is_symlink() else None
        for vdir in sorted(photo.glob("v[0-9][0-9][0-9]")):
            if vdir.name != current_target:
                shutil.rmtree(vdir)
                actions.append(f"pruned {photo.name}/{vdir.name}")
    return actions
```

- [ ] **Step 4: PASS full suite. Step 5: Commit.**

### Task 15: CLI wiring — render/verify/publish/status end-to-end

**Files:**
- Modify: `pipeline/__main__.py`
- Create: `pipeline/driver.py`, `tests/test_driver.py`

**Interfaces:**
- Consumes: every prior module.
- Produces: `driver.render_photo(stem) -> Path` (staging dir with all 22 artifacts: 3 RT TIF renders; native JPG per style via `crops.jpg_from_tif` with no crop/resize; crop JPGs using recipe crop windows — `geometry.centered_crop` default if recipe window is None, with the safe-edge check from `geometry.validate_crop`; `metadata.strip` on every JPG; 9 `pdfs.wrap` + `pdfs.comparison_sheet`); `driver.verify_photo(stem) -> list[str]`; `driver.approve(stem)` (computes and stores fingerprint in recipe + manifest, sets state approved — called by the operator after visual review); `driver.process_all()` (lock → toolchain verify → recover → for each photo advance states: ingest handled by Task 8's command; preview_ready → prints "review required"; approved → render → verify → publish → verified; fingerprint mismatch handled by `manifest.effective_state`). CLI subcommands: `render <stem>`, `verify <stem>`, `approve <stem>`, `publish <stem>`, `run`, `status` (real listing now).

- [ ] **Step 1: Write the failing test** (state-flow logic only; external tools monkeypatched)

```python
import pytest
from pipeline import driver, manifest, toolchain

@pytest.fixture(autouse=True)
def _no_real_toolchain(monkeypatch):
    monkeypatch.setattr(toolchain, "verify", lambda p: [])

def test_run_blocks_unapproved(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "preview_ready")
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    calls = []
    monkeypatch.setattr(driver, "render_photo", lambda s: calls.append(s))
    driver.process_all()
    assert calls == []                    # nothing rendered without approval

def test_approved_photo_flows_to_verified(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda s: tmp_repo / "staging" / f"{s}.tmp")
    monkeypatch.setattr(driver, "verify_photo", lambda s: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda s: None)
    driver.process_all()
    assert manifest.load()["photos"]["P1"]["state"] == "verified"

def test_fingerprint_change_demotes(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "old"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "new")
    monkeypatch.setattr(driver, "render_photo", lambda s: (_ for _ in ()).throw(AssertionError))
    driver.process_all()
    assert manifest.load()["photos"]["P1"]["state"] == "review_required"
```

- [ ] **Step 2: FAIL. Step 3: Implement `driver.py`**

```python
import json, subprocess
from pathlib import Path
from . import (paths, labprofile, toolchain, recipe, manifest, render,
               crops, geometry, metadata, pdfs, verify as verify_mod, publish)

LAB_PROFILE = "generic-v1"

def _lab():
    return labprofile.load(LAB_PROFILE)

def _lock():
    return json.loads((paths.config_dir() / "toolchain.lock").read_text())

def _current_fingerprint(stem):
    rec = recipe.load(stem)
    return recipe.fingerprint(stem, rec, render.style_hashes(stem),
                              render.seed_hash(), _lock(), _lab())

def _dims(tif):
    out = subprocess.run(["magick", "identify", "-format", "%w %h", str(tif)],
                         capture_output=True, text=True).stdout.split()
    return int(out[0]), int(out[1])

def render_photo(stem):
    rec = recipe.load(stem)
    lab = _lab()
    raw = paths.archive_dir() / f"{stem}.rw2"
    staging = paths.staging_dir() / f"{stem}.tmp"
    if staging.exists():
        import shutil; shutil.rmtree(staging)
    staging.mkdir(parents=True)
    native_jpgs = {}
    for style in paths.STYLES:
        tif = staging / f"{stem}_{style}.tif"
        render.rt_render(raw, style, tif, "tif16", None)
        w, h = _dims(tif)
        landscape = w >= h
        native = staging / f"{stem}_{style}.jpg"
        crops.jpg_from_tif(tif, native, None, None,
                           rec["sharpen"]["native"], lab["jpeg_quality"], lab["ppi"])
        native_jpgs[style] = native
        for c in paths.CROPS:
            win = rec["crops"].get(c) or geometry.centered_crop(w, h, c, landscape)
            geometry.validate_crop(win, w, h, c, landscape)
            target = geometry.target_pixels(c, landscape, lab["ppi"])
            crops.jpg_from_tif(tif, staging / f"{stem}_{style}_{c}.jpg", win, target,
                               rec["sharpen"][c], lab["jpeg_quality"], lab["ppi"])
    for jpg in staging.glob("*.jpg"):
        metadata.strip(jpg, lab["keep_capture_date"])
    for jpg in sorted(staging.glob("*.jpg")):
        stem_style = jpg.stem
        crop = next((c for c in paths.CROPS if stem_style.endswith(f"_{c}")), None)
        w, h = _dims(jpg)
        pdfs.wrap(jpg, jpg.with_suffix(".pdf"),
                  geometry.pdf_page_inches(crop, w, h, lab["ppi"], w >= h))
    pdfs.comparison_sheet(stem, native_jpgs, staging)
    return staging

def verify_photo(stem):
    rec = recipe.load(stem)
    return verify_mod.photo(stem, paths.staging_dir() / f"{stem}.tmp", rec, _lab(),
                            landscape=None)

def approve(stem):
    fp = _current_fingerprint(stem)
    rec = recipe.load(stem)
    import datetime
    rec["approval"] = {"fingerprint": fp,
                       "approved_at": datetime.datetime.now().isoformat(timespec="seconds")}
    recipe.save(stem, rec)
    m = manifest.load()
    manifest.set_state(m, stem, "approved")
    m["photos"][stem]["fingerprint"] = fp
    manifest.save(m)

def _publish_photo(stem):
    prov = {"fingerprint": _current_fingerprint(stem), "toolchain": _lock()}
    publish.publish(stem, paths.staging_dir() / f"{stem}.tmp", prov)
    publish.rebuild_views()

def process_all():
    with publish.acquire_lock():
        problems = toolchain.verify(paths.config_dir() / "toolchain.lock")
        if problems:
            raise RuntimeError(f"toolchain drift, refusing to render: {problems}")
        publish.recover()
        m = manifest.load()
        for stem in sorted(m["photos"]):
            fp = _current_fingerprint(stem)
            state = manifest.effective_state(m, stem, fp)
            if state != m["photos"][stem]["state"]:
                manifest.set_state(m, stem, state)
                manifest.save(m)
            if state == "ingested":
                render.ensure_sidecar_all(stem)
                for s in paths.STYLES:
                    render.preview(stem, s)
                manifest.set_state(m, stem, "preview_ready")
                manifest.save(m)
                print(f"{stem}: previews ready — visual review required")
            elif state in ("preview_ready", "review_required"):
                print(f"{stem}: awaiting visual review + approve")
            elif state == "approved":
                render_photo(stem)
                problems = verify_photo(stem)
                if problems:
                    print(f"{stem}: VERIFY FAILED\n  " + "\n  ".join(problems))
                    continue
                _publish_photo(stem)
                manifest.set_state(m, stem, "verified")
                manifest.save(m)
                print(f"{stem}: verified and published")
```

Add `render.ensure_sidecar_all(stem)` (loops `ensure_sidecar` over `paths.STYLES`) to `render.py`. Wire all subcommands in `__main__.py`; `status` prints each photo's effective state. Note `toolchain.verify` compares only entries present in the lock; a `verify_tools`-only drift should print a warning but not block — implement by splitting `problems` on tool class using `toolchain.VERIFY_TOOLS` membership.

- [ ] **Step 4: PASS full suite. Step 5: Commit.**

### Task 16: End-to-end run on the real photos + operational review loop doc

**Files:**
- Create: `docs/superpowers/review-loop.md`

- [ ] **Step 1: Full pipeline dry run to the review gate**

```bash
scripts/process.sh run
```
Expected: both photos reach `preview_ready`; six preview JPGs exist in `previews/`; `scripts/process.sh status` lists both stems as awaiting review.

- [ ] **Step 2: Document the operational review loop**

Write `docs/superpowers/review-loop.md` with exactly this content (this is the runbook the operator follows for every photo — the plan cannot pre-decide edits, but it fixes the procedure):

```markdown
# Visual Review Loop (operator runbook)

Per photo, per style:
1. Read `previews/<stem>_<style>_preview.jpg` at full size.
2. Judge: exposure, white balance/skin tones, highlight retention, shadow
   detail, style intent (natural = faithful; filmic = subtly warm; bw =
   tonal separation on faces).
3. If adjustment needed, edit `sidecars/<stem>_<style>.pp3` (plain INI,
   layered over the base style). Common keys:
   [Exposure] Compensation=0.15
   [White Balance] Setting=Custom / Temperature=5400 / Green=1.0
   [Shadows & Highlights] Enabled=true / Highlights=12 / Shadows=8
   [Vibrance] Pastels=8
   [Black & White] MixerRed=35 (bw only)
4. Re-run `scripts/process.sh preview <stem> <style>` and re-Read. Iterate
   until it holds up.
5. Expression audit (once per photo, on the natural preview): per person —
   eyes open? natural smile? looking at camera? Record findings in
   recipes/<stem>.yaml under expression_audit as strings
   ("subject 2nd from left: eyes half closed").
6. Crop review: default centered crops are computed automatically; check
   them by rendering (`scripts/process.sh render <stem>` after approve, or
   crop test via previews). If a default crop clips heads/hands or violates
   the 2% safe edge, write the corrected window into recipes/<stem>.yaml
   under crops: {x, y, w, h in source pixels}.
7. When all three styles + crops hold up: `scripts/process.sh approve <stem>`
   then `scripts/process.sh run` to render → verify → publish.
8. Commit the recipe + sidecars after each photo's approval.
```

- [ ] **Step 3: Execute the review loop for both photos** (operator work, using the runbook above). This step is done when both photos are `verified`:

```bash
scripts/process.sh status
```
Expected: `P1036163: verified`, `P1036170: verified`; `Output/photos/<stem>/current/` contains 22 files + provenance.json each; `Output/TIF|JPG|PDF/` views populated (3/9/10 links per photo... TIF view: 6 total, JPG view: 18 total, PDF view: 20 total for two photos).

- [ ] **Step 4: Final full-suite + quality gate**

Run: `.venv/bin/python -m pytest -v` → all PASS. Read one published deliverable of each type (a TIF via preview conversion if needed, a JPG, the comparison sheet source) to confirm final visual quality.

- [ ] **Step 5: Commit** all recipes, sidecars, runbook; update HANDOFF.md.

---

## Self-Review Notes

- **Spec coverage:** state machine (T7/T15), ingest preflight contract (T8), geometry table (T4/T10), lab profile fields + classes (T3), fingerprint inputs incl. RAW/seed/styles/render-tools/review-fields (T6), artifact-level deps incl. verify-only tools (T7/T15), atomic vNNN + current swap + recovery + lockfile (T14), RT isolation via XDG seed copy + explicit -p chains (T9), sharpening after resample (T10 command order), metadata allowlist scoped to descriptive groups (T11), PDF losslessness by extraction hash + page boxes + qpdf-is-syntactic (T12/T13), comparison sheet with committed composite source (T12), max_file_bytes fail-don't-degrade (T13 check_image), expression audit + ranking (T16 runbook + recipe field), Checkpoint 1 gate incl. orientation/lens/highlights and both files (T1), toolchain.lock committed (T5), views (T14), single-machine reproduction (T5+T6+T14 provenance). Descoped items (concurrency beyond lockfile, cross-machine, Topaz modeling) intentionally absent per spec.
- **Known simplification:** `manifest.artifact_deps` stores per-artifact dep records; T15's re-render decisions derive from the photo-level fingerprint plus artifact dep comparison — sufficient for the spec's invalidation examples.
- **Type consistency check:** `paths` accessors are functions after the Task 3 refactor (`paths.input_dir()` etc.); Tasks 8–15 are written against the function forms. Task 2 initially defines constants; Task 3 refactors and updates Task 2's files — implementers of later tasks use the function forms shown in their own task code.
```
