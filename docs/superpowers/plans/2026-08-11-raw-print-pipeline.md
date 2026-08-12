# RAW → Print-Ready Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Rev 2** — incorporates all findings from the Codex plan review (RT env/profile
corrections, publication allowlist, deliverable-wide metadata QA, structured
toolchain verification, normalized crop geometry, full CLI wiring).

> **Companion file:** wherever a task below says "as rev 1" or "rev 1's tests",
> the complete code and test blocks are in
> `docs/superpowers/plans/2026-08-11-raw-print-pipeline-rev1.md` under the SAME
> task number. Read that section, then apply this file's stated changes on top.
> Where the two conflict, THIS file wins. Implementers must consult both files
> for any task that references rev 1.

**Goal:** Build a repeatable pipeline that turns Panasonic GH7 `.rw2` files in `Input/` into 22 verified print-ready outputs per photo (3 TIF masters, 9 JPGs, 10 PDFs), with a human-in-the-loop visual review gate.

**Architecture:** A Python package (`pipeline/`) driven by `scripts/process.sh`, orchestrating external tools: rawtherapee-cli (RAW decode with layered plain-text `.pp3` profiles: committed base style + per-image override), ImageMagick (crops/resample/sharpen/JPG), img2pdf (lossless PDF wrap), exiftool (metadata), qpdf + poppler (PDF QA). State lives in committed per-photo recipes plus a derived gitignored `.manifest` (rebuildable from recipes + published provenance); publishes are allowlisted immutable `vNNN` dirs behind an atomically-swapped `current` symlink.

**Tech Stack:** Python 3 (venv, pytest, PyYAML), zsh entrypoint, Homebrew-installed image tools.

## Global Constraints

Copied from spec (`docs/superpowers/specs/2026-08-11-raw-print-pipeline-design.md`, rev 6):

- All deliverables sRGB. TIF masters: 16-bit, Deflate/zip compression, native pixels, native ratio only, NOT subject to lab `max_file_bytes`.
- JPG: quality 92, 300 PPI tags (both axes + unit inches). Crops resample to EXACT pixels: 8×10 → 2400×3000 (portrait) / 3000×2400 (landscape); 5×7 → 1500×2100 / 2100×1500. Native JPG: no resampling. All resampling is downsampling, Lanczos. Never upscale.
- Output sharpening AFTER the final resample. No sharpening inside the RAW render (base pp3s contain no `[Sharpening]` section) — the ImageMagick `-unsharp` after resize is the only sharpening.
- PDFs wrap JPGs via img2pdf, zero re-encoding; page box exactly equals print size; comparison sheet is landscape US Letter (792×612 pts) from a 3300×2550 composite.
- Naming: `<stem>_<style>[_<crop>].<ext>`; styles `natural|filmic|bw`; crops `8x10|5x7`.
- rawtherapee-cli: explicit `-p` chains only (base style, then optional generated override profiles, then per-image sidecar), never `-d`; isolation via `RT_SETTINGS`/`RT_CACHE` env vars pointing into `run/` (RawTherapee's documented custom-path mechanism — NOT `XDG_CONFIG_HOME`).
- Exactly 22 published files per photo + `provenance.json` — publication is allowlist-based; QA scratch and comparison-source files never publish.
- Metadata allowlist applies to ALL deliverables (TIF + JPG; PDFs checked for empty document-info): descriptive namespaces EXIF/XMP/IPTC/MakerNotes only; allowed tags: Orientation, ExposureTime, FNumber, ISO, FocalLength, LensModel, DateTimeOriginal (per lab profile), Copyright, XResolution, YResolution, ResolutionUnit. ICC + structural tags preserved.
- Oversized JPG (> lab `max_file_bytes`) FAILS verification for manual resolution.
- Driver lockfile `run/driver.lock` (pid inside; stale-pid detection).
- Tool discovery: rawtherapee-cli at `/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli` OR on `PATH` (`shutil.which`) — resolved once in `paths.rt_cli()`.
- Python: `.venv/bin/python`; tests `.venv/bin/python -m pytest`.
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Visual verification steps require the worker to Read the referenced image and describe what they see.
- **Explicit descopes (per spec Scope boundaries):** no double-render reproduction test (single-machine; archive re-hash before render is the implemented guard); no cross-machine portability; concurrency = lockfile only.

## File Structure

Same modules as rev 1, plus structured returns and helpers noted per task:

```
scripts/process.sh, pipeline/{__init__,__main__,paths,labprofile,geometry,
toolchain,recipe,manifest,ingest,render,crops,metadata,pdfs,verify,publish,
driver}.py, config/{lab-profiles/generic-v1.yaml,styles/*.pp3,
rawtherapee-seed/options,toolchain.lock}, tests/*, docs/superpowers/review-loop.md
```

---

### Task 1: Checkpoint 1 — install tools and verify GH7 decode (GATE)

No code. Findings go in the Task 2 commit message.

- [ ] **Step 1: Install tools**

```bash
brew install --cask rawtherapee
brew install exiftool imagemagick img2pdf qpdf poppler
```

If the cask fails, download the official dmg from rawtherapee.com, install to /Applications, and note that RawTherapee's macOS release ships `rawtherapee-cli` as a separate binary that may need copying next to the app or onto PATH — verify Step 2 finds it either way.

- [ ] **Step 2: Verify CLI presence and versions**

```bash
RT="/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli"
[ -x "$RT" ] || RT="$(which rawtherapee-cli)"
echo "RT_CLI=$RT" && "$RT" --version
exiftool -ver && magick --version | head -1 && img2pdf --version && qpdf --version && pdfinfo -v 2>&1 | head -1 && pdfimages -v 2>&1 | head -1
```

Expected: every command prints a version. Record RT's exact version — pp3 `Version=` in Task 9 must match its ppversion (352 for RT 5.12; confirm for the installed version by exporting any pp3 from a test render and reading its header).

- [ ] **Step 3: Neutral decode of both GH7 files**

```bash
mkdir -p previews
"$RT" -o previews/checkpoint_neutral_63.jpg -j92 -Y -c Input/P1036163.rw2
"$RT" -o previews/checkpoint_neutral_70.jpg -j92 -Y -c Input/P1036170.rw2
magick identify previews/checkpoint_neutral_63.jpg previews/checkpoint_neutral_70.jpg
```

Expected: exit 0, both JPGs ≈ 5776x4336 (or rotated). If RT cannot decode the RW2, STOP the plan and report — fallback chain (darktable → rawpy) triggers a re-plan.

- [ ] **Step 4: Visual verification (Read both JPGs)**

Read both files. Confirm and record: plausible skin tones (no magenta/green cast), correct orientation (people upright), no artifacts (banding, stuck tiles).

- [ ] **Step 5: Lens-correction and highlight-recovery A/B**

```bash
printf '[LensProfile]\nLcMode=lfauto\nUseDistortion=true\nUseVignette=true\nUseCA=true\n' > /tmp/lens_on.pp3
printf '[HLRecovery]\nEnabled=true\nMethod=Coloropp\n' > /tmp/hl_on.pp3
printf '[HLRecovery]\nEnabled=false\n' > /tmp/hl_off.pp3
"$RT" -o previews/checkpoint_lens.jpg -j92 -Y -p /tmp/lens_on.pp3 -c Input/P1036163.rw2
"$RT" -o previews/checkpoint_hl_on.jpg -j92 -Y -p /tmp/hl_on.pp3 -c Input/P1036163.rw2
"$RT" -o previews/checkpoint_hl_off.jpg -j92 -Y -p /tmp/hl_off.pp3 -c Input/P1036163.rw2
```

Read and compare: `checkpoint_lens.jpg` vs neutral (`lfauto` = automatic lensfun match; if geometry is identical AND `"$RT" -Y -p /tmp/lens_on.pp3 ...` stderr shows a lens-match warning, record that the GH7 lens is not in the lensfun DB and lens correction relies on the embedded MFT corrections RT applies at decode — acceptable, but must be recorded, not assumed). Compare `hl_on` vs `hl_off` in the brightest areas (sky/skin highlights): recovery-on should retain more highlight detail. Record observations.

### Task 2: Scaffolding — venv, package skeleton, entrypoint, first test

**Files:**
- Create: `scripts/process.sh`, `pipeline/__init__.py`, `pipeline/__main__.py`, `pipeline/paths.py`, `requirements-dev.txt`, `tests/conftest.py`, `tests/test_cli.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `paths.root() -> Path` (reads `PIPELINE_ROOT` env or repo root); accessor functions `paths.input_dir() / output_dir() / archive_dir() / staging_dir() / run_dir() / recipes_dir() / sidecars_dir() / previews_dir() / config_dir() / manifest_path()`; `paths.rt_cli() -> str` (bundle path if executable, else `shutil.which("rawtherapee-cli")`, else raises `RuntimeError`); constants `paths.STYLES = ("natural", "filmic", "bw")`, `paths.CROPS = ("8x10", "5x7")`; CLI `python -m pipeline status`.

- [ ] **Step 1: venv + requirements + gitignore**

```bash
python3 -m venv .venv && .venv/bin/pip -q install pytest pyyaml
printf 'pytest\npyyaml\n' > requirements-dev.txt
printf '.venv/\n__pycache__/\n' >> .gitignore
```

- [ ] **Step 2: Write the failing test**

`tests/conftest.py`:
```python
import pytest

@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
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

- [ ] **Step 3: Run to verify FAIL** — `.venv/bin/python -m pytest tests/test_cli.py -v` → `No module named pipeline`.

- [ ] **Step 4: Implement**

`pipeline/__init__.py`: empty.

`pipeline/paths.py`:
```python
import os, shutil
from pathlib import Path

STYLES = ("natural", "filmic", "bw")
CROPS = ("8x10", "5x7")
_RT_BUNDLE = "/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli"

def root():
    return Path(os.environ.get("PIPELINE_ROOT",
                Path(__file__).resolve().parent.parent))

def input_dir():    return root() / "Input"
def output_dir():   return root() / "Output"
def archive_dir():  return root() / "archive"
def staging_dir():  return root() / "staging"
def run_dir():      return root() / "run"
def recipes_dir():  return root() / "recipes"
def sidecars_dir(): return root() / "sidecars"
def previews_dir(): return root() / "previews"
def config_dir():   return root() / "config"
def manifest_path(): return root() / ".manifest"

def rt_cli():
    if os.access(_RT_BUNDLE, os.X_OK):
        return _RT_BUNDLE
    p = shutil.which("rawtherapee-cli")
    if p:
        return p
    raise RuntimeError("rawtherapee-cli not found (bundle or PATH)")
```

`pipeline/__main__.py` (minimal now; Task 15 completes it):
```python
import argparse

def cmd_status(args):
    print("photos: (manifest not yet implemented)")
    return 0

def build_parser():
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    return ap

def main(argv=None):
    ns = build_parser().parse_args(argv)
    return ns.fn(ns)

if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/process.sh`:
```bash
#!/bin/zsh
exec "$(dirname "$0")/../.venv/bin/python" -m pipeline "$@"
```
`chmod +x scripts/process.sh`

- [ ] **Step 5: PASS + commit** (include Checkpoint 1 findings in the message).

### Task 3: Lab profile module + generic-v1

**Files:** Create `pipeline/labprofile.py`, `config/lab-profiles/generic-v1.yaml`, `tests/test_labprofile.py`

**Interfaces:**
- Produces: `labprofile.load(name) -> dict` (ValueError on missing/unknown fields); `REVIEW_FIELDS = {"safe_edge_percent", "bleed", "color_space", "ppi"}`; `RENDER_FIELDS = {"submission_format", "jpeg_quality", "embed_icc", "max_file_bytes", "filename_rules", "strip_metadata_beyond_allowlist", "keep_capture_date"}`; `ORDER_FIELDS = {"lab_color_correction", "checkout_crop_review"}`; `review_view(p)` / `render_view(p)`; `labprofile.check_filename(name: str, p) -> str | None` (violation message for non-ASCII or > 64 chars — used by verify).

Same YAML content as spec. Tests: load values; field-class partition covers all keys; views; missing-field raises; `check_filename("ok.jpg", p) is None` and `check_filename("x"*70 + ".jpg", p)` returns a message.

- [ ] **Step 1: Write the failing test** (as above, four tests plus:)

```python
def test_check_filename():
    p = labprofile.load("generic-v1")
    assert labprofile.check_filename("P1_natural.jpg", p) is None
    assert labprofile.check_filename("x" * 70 + ".jpg", p) is not None
    assert labprofile.check_filename("café.jpg", p) is not None
```

- [ ] **Step 2: FAIL. Step 3: Implement** — as rev 1 Task 3 plus:

```python
def check_filename(name, p):
    if len(name) > 64:
        return f"{name}: exceeds 64 chars"
    if not name.isascii():
        return f"{name}: non-ASCII"
    return None
```

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 4: Geometry module (pure math, normalized windows)

**Files:** Create `pipeline/geometry.py`, `tests/test_geometry.py`

**Interfaces:**
- Produces: `target_pixels(crop, landscape, ppi) -> (w, h)`; `centered_crop_norm(w, h, crop, landscape) -> dict` — NORMALIZED floats `{"x", "y", "w", "h"}` in 0..1 of source dims (what recipes store, per spec "normalized crop geometry"); `to_pixels(norm: dict, w: int, h: int) -> dict` (int pixel window); `validate_crop(norm, w, h, crop, landscape, ppi) -> None` (raises ValueError: out of bounds / aspect off > 0.5 % / pixel window smaller than `target_pixels(..., ppi)` = upscale); `pdf_page_inches(crop, w, h, ppi, landscape)`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from pipeline import geometry

def test_target_pixels():
    assert geometry.target_pixels("8x10", False, 300) == (2400, 3000)
    assert geometry.target_pixels("8x10", True, 300) == (3000, 2400)
    assert geometry.target_pixels("5x7", False, 300) == (1500, 2100)
    assert geometry.target_pixels("5x7", True, 300) == (2100, 1500)

def test_centered_norm_roundtrip():
    n = geometry.centered_crop_norm(5776, 4336, "8x10", True)
    px = geometry.to_pixels(n, 5776, 4336)
    assert px["h"] == 4336 and px["w"] == 5420   # 4336*10/8
    assert px["x"] == (5776 - 5420) // 2 and px["y"] == 0
    geometry.validate_crop(n, 5776, 4336, "8x10", True, 300)  # no raise

def test_validate_rejects_out_of_bounds():
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0.9, "y": 0.0, "w": 0.5, "h": 1.0},
                               5776, 4336, "8x10", True, 300)

def test_validate_rejects_upscale():
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0.0, "y": 0.0, "w": 0.3, "h": 0.3},
                               5776, 4336, "8x10", True, 300)

def test_validate_respects_ppi():
    n = geometry.centered_crop_norm(5776, 4336, "8x10", True)
    with pytest.raises(ValueError):                # 600 PPI needs 6000x4800
        geometry.validate_crop(n, 5776, 4336, "8x10", True, 600)

def test_pdf_page_inches():
    assert geometry.pdf_page_inches("8x10", 2400, 3000, 300, False) == (8.0, 10.0)
    assert geometry.pdf_page_inches(None, 5776, 4336, 300, True) == (5776/300, 4336/300)
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
SIZES = {"8x10": (8, 10), "5x7": (5, 7)}

def target_pixels(crop, landscape, ppi):
    a, b = SIZES[crop]
    return (b * ppi, a * ppi) if landscape else (a * ppi, b * ppi)

def centered_crop_norm(w, h, crop, landscape):
    tw, th = target_pixels(crop, landscape, 300)
    aspect = tw / th
    if w / h > aspect:
        ch, cw = h, round(h * aspect)
    else:
        cw, ch = w, round(w / aspect)
    return {"x": (w - cw) / 2 / w, "y": (h - ch) / 2 / h, "w": cw / w, "h": ch / h}

def to_pixels(n, w, h):
    return {"x": round(n["x"] * w), "y": round(n["y"] * h),
            "w": round(n["w"] * w), "h": round(n["h"] * h)}

def validate_crop(n, w, h, crop, landscape, ppi):
    if not (0 <= n["x"] and 0 <= n["y"] and n["x"] + n["w"] <= 1.0001
            and n["y"] + n["h"] <= 1.0001):
        raise ValueError(f"crop window out of bounds: {n}")
    px = to_pixels(n, w, h)
    tw, th = target_pixels(crop, landscape, ppi)
    if abs((px["w"] / px["h"]) - (tw / th)) / (tw / th) > 0.005:
        raise ValueError(f"crop window aspect mismatch: {px}")
    if px["w"] < tw or px["h"] < th:
        raise ValueError(f"crop window would require upscaling at {ppi} PPI: {px}")

def pdf_page_inches(crop, w, h, ppi, landscape):
    if crop is None:
        return (w / ppi, h / ppi)
    a, b = SIZES[crop]
    return (float(b), float(a)) if landscape else (float(a), float(b))
```

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 5: Toolchain lock (structured, with assets)

**Files:** Create `pipeline/toolchain.py`, `tests/test_toolchain.py`. The real `config/toolchain.lock` is generated in Task 9 Step 5 (after styles/seed/font choices exist), not here.

**Interfaces:**
- Produces: `toolchain.discover() -> dict` — entries for tools `rawtherapee, magick, img2pdf, qpdf, exiftool, pdfimages, pdfinfo` (`{"path","version","sha256"}`) plus assets `font` (`/System/Library/Fonts/Helvetica.ttc`) and `rt_icc` (the `RTv4_sRGB` output profile found by `glob` under the RT app bundle's `Resources` — record its path + sha256; if the running RT is not the bundle, glob relative to `Path(paths.rt_cli()).parent.parent`); `write_lock(entries, path)`; `verify(path) -> list[dict]` — structured `{"name": str, "problem": str}`; class sets `RENDER_TOOLS = {"rawtherapee", "rt_icc"}`, `CROP_TOOLS = {"magick", "font"}`, `PDF_TOOLS = {"img2pdf"}`, `VERIFY_TOOLS = {"qpdf", "pdfimages", "pdfinfo", "exiftool"}`; `entries_for(lock, names)`.

- [ ] **Step 1: Write the failing test**

```python
import json
from pipeline import toolchain

FAKE = {"rawtherapee": {"path": "/x", "version": "5.12", "sha256": "aa"},
        "magick": {"path": "/y", "version": "7.1", "sha256": "bb"}}

def test_write_and_verify_roundtrip(tmp_path):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    assert json.loads(lock.read_text()) == FAKE

def test_verify_structured_mismatch(tmp_path, monkeypatch):
    lock = tmp_path / "toolchain.lock"
    toolchain.write_lock(FAKE, lock)
    monkeypatch.setattr(toolchain, "discover", lambda: {**FAKE,
        "magick": {"path": "/y", "version": "7.2", "sha256": "cc"}})
    problems = toolchain.verify(lock)
    assert problems == [{"name": "magick",
                         "problem": "hash mismatch (5.12? 7.1 -> 7.2)"}] or (
        len(problems) == 1 and problems[0]["name"] == "magick")

def test_class_sets_cover_all_locked_names():
    all_names = (toolchain.RENDER_TOOLS | toolchain.CROP_TOOLS |
                 toolchain.PDF_TOOLS | toolchain.VERIFY_TOOLS)
    assert {"rawtherapee", "magick", "img2pdf", "qpdf", "exiftool",
            "pdfimages", "pdfinfo", "font", "rt_icc"} == all_names

def test_entries_for_subsets():
    assert set(toolchain.entries_for(FAKE, {"magick"})) == {"magick"}
```

- [ ] **Step 2: FAIL. Step 3: Implement** — as rev 1 Task 5 with these changes: `_VERSION_ARGS` adds `"pdfinfo": ["-v"]`; `discover()` appends the two asset entries (no version subprocess for assets — `"version": "asset"`); `verify()` returns `[{"name": n, "problem": f"hash mismatch ({old} -> {new})"} , ...]` dicts; asset discovery:

```python
def _rt_icc_path():
    bundle = Path(_tool_path("rawtherapee")).parent.parent
    hits = sorted(bundle.rglob("RTv4_sRGB*"))
    if not hits:
        raise RuntimeError("RTv4_sRGB output profile not found in RT bundle")
    return hits[0]
```

- [ ] **Step 4: Unit tests PASS (no lock generation yet). Step 5: Commit.**

### Task 6: Recipe module + approval fingerprint

**Files:** Create `pipeline/recipe.py`, `tests/test_recipe.py`

**Interfaces:**
- Produces: `recipe.new(stem, raw_sha256, width, height) -> dict` — adds source `width`/`height` from ingest, plus `manual_assets: []` (list of `{"file": str, "sha256": str}` for any Photoshop/Topaz raster; a non-empty list marks the photo outside automated re-render per spec scope boundary); crops stored as NORMALIZED windows or None; the rest as rev 1 (`overrides`, `sharpen` defaults, `expression_audit`, `approval`).
- `recipe.load/save`, `recipe.file_hashes`, `recipe.fingerprint(stem, rec, style_hashes, seed_hash, lock, lab)` — fingerprint material additionally includes `rec["manual_assets"]`; render-tool entries come from `toolchain.entries_for(lock, toolchain.RENDER_TOOLS)` (now includes `rt_icc`).

- [ ] **Steps 1–5:** Same test suite as rev 1 Task 6 (deterministic; crop-sensitive; order-field-insensitive; render-tool-sensitive; verify-tool-insensitive — use `magick` as the verify-class control since `font` is crop-class; roundtrip), with `recipe.new("P1", "rawhash", 5776, 4336)` signatures, plus:

```python
def test_fingerprint_sensitive_to_manual_assets():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    a = _fp(rec)
    rec["manual_assets"].append({"file": "P1_retouch.tif", "sha256": "mm"})
    assert _fp(rec) != a
```

Implementation identical in structure to rev 1 with the added fields. PASS, commit.

### Task 7: Manifest + state machine + artifact dependencies + rebuild

**Files:** Create `pipeline/manifest.py`, `tests/test_manifest.py`

**Interfaces:**
- As rev 1 (`STATES`, `load/save`, `set_state`, `effective_state`, `artifact_names` → 22 names, `artifact_deps`) with:
  - `artifact_deps` uses lock-entry classes: TIF ← raw/style/seed/RENDER_TOOLS entries; JPG adds lab render fields + CROP_TOOLS entries + normalized crop + sharpen; PDF adds PDF_TOOLS; sheet ← three native JPG names. (Same code shape as rev 1.)
  - NEW `manifest.record_artifacts(m, stem, deps_by_name: dict)` — stores the per-artifact dep records under `m["photos"][stem]["artifacts"]` at render time.
  - NEW `manifest.stale_artifacts(m, stem, current_deps_by_name) -> list[str]` — names whose stored deps ≠ current.
  - NEW `manifest.rebuild() -> dict` — reconstructs `.manifest` with no cache: for each `recipes/*.yaml`: state `verified` if `Output/photos/<stem>/current/provenance.json` exists AND its `fingerprint` matches the recipe's `approval.fingerprint`; else `approved` if the recipe has an approval fingerprint; else `ingested`. Artifact records restored from provenance.
- Produces for driver: verify-tool drift handled by the driver comparing `toolchain.verify` problems' names against `VERIFY_TOOLS` (re-verify, not re-render).

- [ ] **Step 1: Write the failing test** — rev 1's four tests (22 names; downgrade on fingerprint change; early states untouched; TIF vs JPG deps differ) plus:

```python
def test_record_and_stale(tmp_repo):
    m = manifest.load()
    manifest.set_state(m, "P1", "rendered")
    manifest.record_artifacts(m, "P1", {"P1_natural.tif": {"d": 1},
                                        "P1_natural.jpg": {"d": 2}})
    stale = manifest.stale_artifacts(m, "P1", {"P1_natural.tif": {"d": 1},
                                               "P1_natural.jpg": {"d": 9}})
    assert stale == ["P1_natural.jpg"]

def test_rebuild_from_recipes_and_provenance(tmp_repo):
    import json, yaml
    (tmp_repo / "recipes/P1.yaml").write_text(yaml.safe_dump(
        {"approval": {"fingerprint": "fp", "approved_at": "t"}}))
    cur = tmp_repo / "Output/photos/P1/v001"
    cur.mkdir(parents=True)
    (cur / "provenance.json").write_text(json.dumps(
        {"fingerprint": "fp", "artifacts": {"P1_natural.tif": {"d": 1}}}))
    (tmp_repo / "Output/photos/P1/current").symlink_to("v001")
    m = manifest.rebuild()
    assert m["photos"]["P1"]["state"] == "verified"
    assert m["photos"]["P1"]["artifacts"]["P1_natural.tif"] == {"d": 1}
```

- [ ] **Step 2: FAIL. Step 3: Implement** (rev 1 code plus):

```python
def record_artifacts(m, stem, deps_by_name):
    m["photos"][stem]["artifacts"] = deps_by_name

def stale_artifacts(m, stem, current):
    stored = m["photos"].get(stem, {}).get("artifacts", {})
    return sorted(n for n, d in current.items() if stored.get(n) != d)

def rebuild():
    import json, yaml
    m = {"photos": {}}
    for rp in sorted(paths.recipes_dir().glob("*.yaml")):
        stem = rp.stem
        rec = yaml.safe_load(rp.read_text())
        fp = (rec.get("approval") or {}).get("fingerprint")
        prov_p = paths.output_dir() / "photos" / stem / "current" / "provenance.json"
        m["photos"][stem] = {"state": "ingested", "fingerprint": fp, "artifacts": {}}
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
```

`load()` change: if `.manifest` is missing but `recipes/` is non-empty, call `rebuild()` instead of returning empty.

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 8: Ingest — preflight contract + isolated failures

**Files:** Create `pipeline/ingest.py`, `tests/test_ingest.py`; modify `pipeline/__main__.py` (ingest subcommand).

**Interfaces:**
- `ingest.exif_summary(path) -> dict` (exiftool -j; keys Make, Model, ImageWidth, ImageHeight, Orientation, LensModel, ISO, ExposureTime, plus `AspectRatio` if present — record raw mode/aspect); any subprocess/JSON failure raises `IngestError("<stem>: unreadable metadata: ...")`.
- `ingest.preflight(path, existing_stems, existing_hashes) -> (warnings: list[str], meta: dict)` — duplicate stem → IngestError; content hash in `existing_hashes` → IngestError; missing/zero dims → IngestError; unexpected Make/Model → warning; ISO > 1600 → warning; unrecognized Orientation value → warning.
- `ingest.archive(path, src_sha) -> None` — destination-exists → IngestError (never overwrite); copy, re-hash, mismatch → delete + IngestError; append to SHA256SUMS.
- `ingest.run() -> dict` — every exception (IngestError, OSError) is caught per file; photo marked failed with reason; loop continues; recipe created with `recipe.new(stem, sha, meta["ImageWidth"], meta["ImageHeight"])`.

- [ ] **Step 1: Write the failing test** — rev 1's five tests (clean; high-ISO warn; unexpected-body warn; duplicate-stem raises; archive hash verify) with the new signatures, plus:

```python
def test_preflight_rejects_duplicate_content(monkeypatch):
    monkeypatch.setattr(ingest, "exif_summary", lambda p: dict(GOOD))
    import hashlib
    sha = hashlib.sha256(b"same").hexdigest()
    with pytest.raises(ingest.IngestError):
        ingest.preflight_with_hash("Input/P9.rw2", set(), {sha}, sha)

def test_archive_never_overwrites(tmp_repo):
    src = tmp_repo / "Input/P9.rw2"; src.write_bytes(b"new")
    (tmp_repo / "archive/P9.rw2").write_bytes(b"old")
    with pytest.raises(ingest.IngestError):
        ingest.archive(src, "whatever")

def test_run_isolates_failures(tmp_repo, monkeypatch):
    (tmp_repo / "Input/BAD.rw2").write_bytes(b"a")
    (tmp_repo / "Input/GOOD.rw2").write_bytes(b"b")
    def summary(p):
        if "BAD" in str(p):
            raise ingest.IngestError("BAD: unreadable metadata")
        return dict(GOOD)
    monkeypatch.setattr(ingest, "exif_summary", summary)
    results = ingest.run()
    assert "failed" in results["BAD"] and results["GOOD"] == "ok"
```

(Design note: expose the content-hash duplicate check as `preflight_with_hash(path, stems, hashes, sha)` or fold the sha parameter into `preflight` — implementer's choice, but the test contract above must hold with one consistent signature across `ingest.run`.)

- [ ] **Step 2: FAIL. Step 3: Implement** — rev 1 structure with: try/except around exiftool call re-raising IngestError; `archive(path, src_sha)` computing nothing itself (sha passed in, computed once in `run`); dest-exists guard; `run()` wrapping the whole per-file body in `except (IngestError, OSError) as e`.

- [ ] **Step 4: PASS, then integration:** `scripts/process.sh ingest` → both real photos `ok`; recipes exist with width/height 5776/4336; `archive/SHA256SUMS` has 2 lines. **Step 5: Commit** (recipes committed).

### Task 9: Base styles + RT render wrapper + previews + toolchain.lock generation

**Files:** Create `config/styles/{natural,filmic,bw}.pp3`, `config/rawtherapee-seed/options`, `pipeline/render.py`, `tests/test_render.py`; generate `config/toolchain.lock`.

**Interfaces:**
- `render.rt_render(raw, style, out_path, fmt, quality, extra_profiles=())` — profile chain: base style pp3, then each of `extra_profiles`, then sidecar if present; isolation via env `RT_SETTINGS=<run copy dir>` and `RT_CACHE=<run cache dir>` (RawTherapee's documented mechanism; the run copy is seeded from `config/rawtherapee-seed/options`); `-Y -q`; `tif16` → `-b16 -tz`; `jpg` → `-j<q> -js3`; RenderError on failure/missing output.
- `render.denoise_profile() -> Path` — writes (once per run dir) a pp3 enabling `[Directional Pyramid Denoising] Enabled=true` and returns its path; used when `rec["overrides"]["denoise"]` is true.
- `render.ensure_sidecar(stem, style)`, `render.ensure_sidecar_all(stem)`, `render.preview(stem, style)`, `render.style_hashes(stem)`, `render.seed_hash()` — as rev 1.

- [ ] **Step 1: Base profiles.** `Version=` must match the installed RT's ppversion recorded in Task 1 (352 for 5.12). No `[Sharpening]` section anywhere (Global Constraints).

`config/styles/natural.pp3`:
```ini
[Version]
AppVersion=5.12
Version=352

[White Balance]
Setting=Camera

[Exposure]
Auto=false
Compensation=0
HistogramMatching=true

[Vibrance]
Enabled=true
Pastels=12
Saturated=6
ProtectSkins=true
AvoidColorShift=true

[HLRecovery]
Enabled=true
Method=Coloropp

[LensProfile]
LcMode=lfauto
UseDistortion=true
UseVignette=true
UseCA=true

[Color Management]
OutputProfile=RTv4_sRGB
```

`config/styles/filmic.pp3`: full copy of natural.pp3 with `[White Balance]` replaced by `Setting=Custom / Temperature=5650 / Green=1.0` and `[Exposure]` gaining `CurveMode=Standard` and `Curve=1;0;0;0.12;0.09;0.50;0.52;0.88;0.92;1;1;`.

`config/styles/bw.pp3`: full copy of natural.pp3 plus:
```ini
[Black & White]
Enabled=true
Method=ChannelMixer
Setting=RGB-Rel
MixerRed=28
MixerGreen=52
MixerBlue=20
```

`config/rawtherapee-seed/options`: file containing only the comment line `# immutable RT options seed — copied into run/ (RT_SETTINGS) at render time`.

- [ ] **Step 2: Write the failing test** — rev 1's two tests, with the env assertion changed to `RT_SETTINGS`/`RT_CACHE` and an added `extra_profiles` ordering test:

```python
def test_rt_command_layers_profiles(tmp_repo, monkeypatch):
    ...  # as rev 1, but:
    assert "RT_SETTINGS" in calls["env"] and "RT_CACHE" in calls["env"]

def test_extra_profiles_between_base_and_sidecar(tmp_repo, monkeypatch):
    # arrange base + sidecar + fake run; call with extra_profiles=("/tmp/dn.pp3",)
    # assert -p order: base, /tmp/dn.pp3, sidecar
```
(Write the second test fully, following the first test's fake-subprocess pattern; assert the three `-p` values appear in base → extra → sidecar order.)

- [ ] **Step 3: FAIL, then implement** — rev 1 `render.py` with `_isolated_env` replaced:

```python
def _isolated_env():
    run_dir = paths.run_dir() / f"rt-{uuid.uuid4().hex[:8]}"
    settings = run_dir / "settings"
    cache = run_dir / "cache"
    settings.mkdir(parents=True); cache.mkdir(parents=True)
    seed = paths.config_dir() / "rawtherapee-seed" / "options"
    if seed.exists():
        shutil.copy2(seed, settings / "options")
    return dict(os.environ, RT_SETTINGS=str(settings), RT_CACHE=str(cache))
```

and the profile chain `[base] + list(extra_profiles) + ([sidecar] if exists)`.

- [ ] **Step 4: Unit PASS, then integration:** `scripts/process.sh preview P1036163 natural` (and filmic, bw) — **Read each preview**: natural faithful, filmic slightly warmer, bw monochrome with good facial tonality. If RT rejects a pp3 key or flag (check stderr), fix the key against the installed version's documentation, re-run, record the change. Then generate the lock:

```bash
.venv/bin/python -c "from pipeline import toolchain, paths; toolchain.write_lock(toolchain.discover(), paths.config_dir()/'toolchain.lock'); print('written')"
.venv/bin/python -c "from pipeline import toolchain, paths; print(toolchain.verify(paths.config_dir()/'toolchain.lock') or 'clean')"
```
Expected: `written` then `clean`.

- [ ] **Step 5: Commit** (styles, seed, render.py, sidecars, toolchain.lock).

### Task 10: Crops, resample, output sharpen, JPG export

Identical to rev 1 Task 10 (pure `magick_cmd` builder + `jpg_from_tif` runner; unit tests on command construction; integration renders one real TIF then an 8×10 crop, identify-verified to exactly 3000×2400/2400×3000, **Read** the result). Only change: the integration snippet computes the window via `geometry.centered_crop_norm` + `geometry.to_pixels` and passes lab `ppi` to `validate_crop`.

### Task 11: Metadata strip + allowlist assertion (all raster deliverables)

**Files:** Create `pipeline/metadata.py`, `tests/test_metadata.py`

**Interfaces:** As rev 1 (`ALLOWED`, `DESCRIPTIVE_GROUPS`, `strip(path, keep_capture_date)`, `assert_clean(path, keep_capture_date) -> list`) — applied to BOTH `.jpg` and `.tif` deliverables (exiftool handles both).

- [ ] **Step 1: Write the failing test** — rev 1's two tests plus three more:

```python
def test_strip_preserves_allowed_and_icc(tmp_path):
    p = _make_jpg(tmp_path)
    subprocess.run(["exiftool", "-overwrite_original", "-DateTimeOriginal=2026:07:30 16:11:53", str(p)], check=True)
    metadata.strip(p, keep_capture_date=True)
    out = subprocess.run(["exiftool", "-j", "-ISO", "-DateTimeOriginal", str(p)],
                         capture_output=True, text=True).stdout
    assert "200" in out and "2026:07:30" in out    # survived the strip

def test_strip_drops_capture_date_when_configured(tmp_path):
    p = _make_jpg(tmp_path)
    subprocess.run(["exiftool", "-overwrite_original", "-DateTimeOriginal=2026:07:30 16:11:53", str(p)], check=True)
    metadata.strip(p, keep_capture_date=False)
    out = subprocess.run(["exiftool", "-j", "-DateTimeOriginal", str(p)],
                         capture_output=True, text=True).stdout
    assert "2026:07:30" not in out
    assert metadata.assert_clean(p, keep_capture_date=False) == []

def test_strip_works_on_tif(tmp_path):
    p = tmp_path / "t.tif"
    subprocess.run(["magick", "-size", "32x32", "xc:gray", str(p)], check=True)
    subprocess.run(["exiftool", "-overwrite_original", "-Artist=Somebody", str(p)], check=True)
    metadata.strip(p, keep_capture_date=True)
    assert metadata.assert_clean(p, keep_capture_date=True) == []
```

- [ ] **Steps 2–5:** FAIL → implement (rev 1 code unchanged in structure; `assert_clean` with `keep_capture_date=False` removes DateTimeOriginal from the allowed set) → PASS → commit.

### Task 12: PDFs — img2pdf wraps + comparison sheet (correct montage)

**Files:** Create `pipeline/pdfs.py`, `tests/test_pdfs.py`

**Interfaces:** `pdfs.wrap(jpg, out_pdf, page_inches)` as rev 1; `pdfs.comparison_sheet(stem, native_jpgs, workdir) -> (pdf_path, src_jpg_path)` — TWO ImageMagick steps: (1) `montage` with per-panel geometry `-resize 1000x -geometry +20+40 -tile 3x1 -font Helvetica -pointsize 36 -label <style>` → intermediate; (2) `magick` composite onto exact 3300×2550 white canvas (`-gravity center -background white -extent 3300x2550 -density 300 -units PixelsPerInch -quality 92`) → `<stem>_comparison_src.jpg`; then `wrap(src, pdf, (11.0, 8.5))`. Returns both paths so the driver can keep `src` OUT of the publish allowlist.

- [ ] **Step 1: Write the failing test** — rev 1's `test_wrap_page_box` (576×720 pts) and `test_wrap_is_lossless`, plus:

```python
def test_comparison_sheet_canvas_and_page(tmp_path):
    jpgs = {s: _jpg(tmp_path, f"{s}.jpg") for s in ("natural", "filmic", "bw")}
    pdf, src = pdfs.comparison_sheet("P1", jpgs, tmp_path)
    dims = subprocess.run(["magick", "identify", "-format", "%w %h", str(src)],
                          capture_output=True, text=True).stdout.split()
    assert dims == ["3300", "2550"]                     # exact composite canvas
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    assert "792 x 612" in info                          # landscape US Letter
```

- [ ] **Step 2: FAIL. Step 3: Implement**

```python
def comparison_sheet(stem, native_jpgs, workdir):
    workdir = Path(workdir)
    tiles = workdir / f"{stem}_comparison_tiles.jpg"
    src = workdir / f"{stem}_comparison_src.jpg"
    _run(["magick", "montage",
          "-font", "Helvetica", "-pointsize", "36",
          "-label", "natural", str(native_jpgs["natural"]),
          "-label", "filmic", str(native_jpgs["filmic"]),
          "-label", "bw", str(native_jpgs["bw"]),
          "-tile", "3x1", "-resize", "1000x", "-geometry", "+20+40",
          "-background", "white", str(tiles)])
    _run(["magick", str(tiles), "-background", "white", "-gravity", "center",
          "-extent", "3300x2550", "-density", "300", "-units", "PixelsPerInch",
          "-quality", "92", str(src)])
    tiles.unlink()
    pdf = workdir / f"{stem}_comparison.pdf"
    wrap(src, pdf, (11.0, 8.5))
    return pdf, src
```

- [ ] **Step 4: PASS; Read a generated `_comparison_src.jpg` from the test tmp dir once (re-run one test with `--basetemp=run/pytest-keep`) and confirm three labeled panels centered on a white canvas. Step 5: Commit.**

### Task 13: Verify — QA suite (full deliverable coverage, isolated scratch)

**Files:** Create `pipeline/verify.py`, `tests/test_verify.py`

**Interfaces:**
- `verify.check_image(path, expect_w, expect_h, expect_bits, ppi, max_bytes)` — `max_bytes=None` skips the size cap (TIFs); checks: exists/nonzero, exact dims, bit depth, sRGB ICC description, XResolution AND YResolution == ppi with ResolutionUnit inches (JPG only), TIF adds Compression contains "Deflate"/"Adobe Deflate" (exiftool `-Compression`).
- `verify.check_pdf(pdf, source_jpg, page_pts, scratch_dir)` — as rev 1 PLUS: extraction writes into `scratch_dir` (a `run/qa-<stem>/` dir, NEVER staging), and `pdfinfo` output must show empty/absent Title, Author, Subject, Keywords (document-info hygiene).
- `verify.photo(stem, staging_dir, rec, lab)` — native dims from `rec["width"]/rec["height"]` (ingest ground truth, not the TIF itself); TIF checks with `max_bytes=None` and 16-bit + compression; JPG checks with lab cap + `labprofile.check_filename`; metadata `assert_clean` on every TIF and JPG; unexpected-file check: staging must contain exactly `manifest.artifact_names(stem)` + `{stem}_comparison_src.jpg` + nothing else; scratch dir created under `run/` and removed at the end.

- [ ] **Step 1: Write the failing test** — rev 1's four fixture tests adapted (pass `max_bytes=None` for a no-cap case; wrong-dims; pdf pass with scratch tmp dir; pdf wrong-source) plus:

```python
def test_tif_exempt_from_size_cap(tmp_path):
    p = tmp_path / "big.tif"
    subprocess.run(["magick", "-size", "300x400", "xc:gray", "-depth", "16",
                    "-compress", "Zip", str(p)], check=True)
    assert verify.check_image(p, 300, 400, 16, 300, None) == []

def test_unexpected_file_detected(tmp_repo):
    # build a staging dir with one extra file and assert verify.photo reports it
    ...
```
(Write `test_unexpected_file_detected` fully: create `staging/P1.tmp/` containing only `P1_comparison_src.jpg` plus a rogue `extract-000.jpg`, monkeypatch the per-artifact checks to return [], and assert the rogue file is reported. Follow the monkeypatch pattern used in test_driver.)

- [ ] **Step 2: FAIL. Step 3: Implement** — rev 1 code with the interface changes above; `photo()` skeleton:

```python
def photo(stem, staging_dir, rec, lab):
    from . import geometry, manifest, metadata as md, labprofile
    import shutil
    staging_dir = Path(staging_dir)
    scratch = paths.run_dir() / f"qa-{stem}"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    problems = []
    nw, nh = rec["width"], rec["height"]
    landscape = nw >= nh
    ppi, cap = lab["ppi"], lab["max_file_bytes"]
    expected = set(manifest.artifact_names(stem)) | {f"{stem}_comparison_src.jpg"}
    actual = {p.name for p in staging_dir.iterdir()}
    for extra in sorted(actual - expected):
        problems.append(f"unexpected file in staging: {extra}")
    for missing in sorted(expected - actual):
        problems.append(f"missing artifact: {missing}")
    for name in manifest.artifact_names(stem):
        p = staging_dir / name
        if not p.exists():
            continue
        crop = next((c for c in paths.CROPS if f"_{c}." in name), None)
        if name.endswith(".tif"):
            problems += check_image(p, nw, nh, 16, ppi, None)
            problems += [f"{name}: metadata {v}" for v in md.assert_clean(p, lab["keep_capture_date"])]
        elif name.endswith(".jpg"):
            w, h = (geometry.target_pixels(crop, landscape, ppi) if crop else (nw, nh))
            problems += check_image(p, w, h, 8, ppi, cap)
            problems += [f"{name}: metadata {v}" for v in md.assert_clean(p, lab["keep_capture_date"])]
            v = labprofile.check_filename(name, lab)
            if v:
                problems.append(v)
        elif name.endswith("_comparison.pdf"):
            problems += check_pdf(p, staging_dir / f"{stem}_comparison_src.jpg",
                                  (792, 612), scratch)
        elif name.endswith(".pdf"):
            src = staging_dir / name.replace(".pdf", ".jpg")
            w, h = (geometry.target_pixels(crop, landscape, ppi) if crop else (nw, nh))
            iw, ih = geometry.pdf_page_inches(crop, w, h, ppi, landscape)
            problems += check_pdf(p, src, (round(iw * 72), round(ih * 72)), scratch)
    shutil.rmtree(scratch)
    return problems
```

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 14: Publish — allowlist, stale locks, recovery via provenance, views through current

**Files:** Create `pipeline/publish.py`, `tests/test_publish.py`

**Interfaces:**
- `acquire_lock()` — pid written; on FileExistsError read the pid, `os.kill(pid, 0)`; if the process is gone, remove the stale lock and retake; else LockError.
- `publish(stem, staging_dir, provenance, allowlist: set[str]) -> Path` — moves ONLY allowlisted files (plus generated `provenance.json`) into the fresh `vNNN` dir (create `vNNN.tmp`, `os.rename` each allowlisted file in, write provenance, `os.rename` `vNNN.tmp` → `vNNN`); atomic `current` swap; prune old versions; remaining staging dir (scratch/comparison src) removed after success.
- `rebuild_views()` — symlinks constructed THROUGH the current pointer (`os.path.relpath(photo/"current"/name, view_dir)`, no `resolve()`), so a version swap updates views without rebuilding.
- `recover() -> list[str]` — orphan staging removal; for each photo dir: if `current` is missing/broken but exactly one `vNNN` exists with a valid `provenance.json`, repoint `current` to it (report); prune non-current versions.

- [ ] **Step 1: Write the failing test** — rev 1's five tests updated for the allowlist signature, plus:

```python
def test_publish_excludes_non_allowlisted(tmp_repo):
    d = _stage(tmp_repo, files=("P1_natural.tif", "P1_comparison_src.jpg",
                                "extract-000.jpg"))
    publish.publish("P1", d, {}, {"P1_natural.tif"})
    v = tmp_repo / "Output/photos/P1/v001"
    assert (v / "P1_natural.tif").exists() and (v / "provenance.json").exists()
    assert not (v / "P1_comparison_src.jpg").exists()
    assert not (v / "extract-000.jpg").exists()

def test_stale_lock_reclaimed(tmp_repo):
    lock = tmp_repo / "run/driver.lock"
    lock.write_text("999999")           # almost certainly dead pid
    with publish.acquire_lock():
        pass                            # no LockError raised

def test_recover_repoints_broken_current(tmp_repo):
    import json, os
    v = tmp_repo / "Output/photos/P1/v001"
    v.mkdir(parents=True)
    (v / "provenance.json").write_text(json.dumps({"fingerprint": "fp"}))
    actions = publish.recover()
    assert os.readlink(tmp_repo / "Output/photos/P1/current") == "v001"
    assert any("repointed" in a for a in actions)
```

- [ ] **Step 2: FAIL. Step 3: Implement** per the interface description (rev 1 code as the base; the allowlist loop replaces the whole-directory rename; stale-pid logic in `acquire_lock`; `recover` gains the repoint branch).

- [ ] **Step 4: PASS. Step 5: Commit.**

### Task 15: Driver + complete CLI wiring

**Files:** Create `pipeline/driver.py`, `tests/test_driver.py`; rewrite `pipeline/__main__.py`.

**Interfaces (driver):**
- `_current_fingerprint(stem)`, `_lab()`, `_lock()` as rev 1.
- `current_artifact_deps(stem) -> dict` — `manifest.artifact_deps` evaluated for all 22 names with current inputs.
- `render_photo(stem, only: set[str] | None = None)` — verifies the archived RAW's sha256 equals `rec["raw_sha256"]` before rendering (RuntimeError on mismatch — the implemented single-machine reproduction guard); renders all or only the named artifacts (TIF renders run when any dependent artifact is stale); applies `render.denoise_profile()` via `extra_profiles` when `rec["overrides"]["denoise"]`; crops from recipe normalized windows (default `centered_crop_norm`) validated with lab `ppi`; `metadata.strip` on every TIF and JPG; PDFs after strip (strip-then-wrap so embedded JPEG hashes match).
- `approve(stem)` — REFUSES (RuntimeError) if `rec["expression_audit"]` is empty ("audit before approval"); stores fingerprint + timestamp; sets state.
- `verify_photo(stem)`, `_publish_photo(stem)` — publish allowlist = `set(manifest.artifact_names(stem))`; provenance = `{"fingerprint", "raw_sha256", "toolchain": lock, "artifacts": current_artifact_deps(stem)}`.
- `process_all()` — lock; structured `toolchain.verify` split: problems whose name ∈ `VERIFY_TOOLS` → demote affected `verified` photos to `rendered` (re-verify only) with a warning; any other problem → hard stop. `publish.recover()`; `publish.rebuild_views()` (every startup); state advance per photo: `ingested` → sidecars + previews → `preview_ready`; `preview_ready|review_required` → print awaiting; `approved` → selective render (`manifest.stale_artifacts` decides `only`) → verify → publish → record artifacts → `verified`; `rendered` → verify → publish → `verified`.
- `crop_preview(stem, style, crop) -> Path` — renders the TIF if needed, produces `previews/<stem>_<style>_<crop>_croppreview.jpg` from the recipe (or default) window — the pre-approval crop review command the runbook uses.

**CLI (`__main__.py`) — complete:**

```python
import argparse, sys

def _wrap(fn):
    def inner(ns):
        try:
            return fn(ns) or 0
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return inner

def build_parser():
    from . import driver, manifest, ingest, render
    ap = argparse.ArgumentParser(prog="pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").set_defaults(fn=_wrap(lambda ns: _status()))
    sub.add_parser("ingest").set_defaults(fn=_wrap(lambda ns: _ingest()))
    p = sub.add_parser("preview"); p.add_argument("stem"); p.add_argument("style")
    p.set_defaults(fn=_wrap(lambda ns: print(render.preview(ns.stem, ns.style))))
    p = sub.add_parser("croppreview"); p.add_argument("stem"); p.add_argument("style"); p.add_argument("crop")
    p.set_defaults(fn=_wrap(lambda ns: print(driver.crop_preview(ns.stem, ns.style, ns.crop))))
    p = sub.add_parser("approve"); p.add_argument("stem")
    p.set_defaults(fn=_wrap(lambda ns: driver.approve(ns.stem)))
    p = sub.add_parser("render"); p.add_argument("stem")
    p.set_defaults(fn=_wrap(lambda ns: driver.render_photo(ns.stem)))
    p = sub.add_parser("verify"); p.add_argument("stem")
    p.set_defaults(fn=_wrap(lambda ns: _verify(ns.stem)))
    sub.add_parser("run").set_defaults(fn=_wrap(lambda ns: driver.process_all()))
    return ap

def _status():
    from . import driver, manifest
    m = manifest.load()
    if not m["photos"]:
        print("photos: none ingested")
        return
    for stem in sorted(m["photos"]):
        fp = driver._current_fingerprint(stem)
        print(f"{stem}: {manifest.effective_state(m, stem, fp)}")

def _ingest():
    from . import ingest
    results = ingest.run()
    for stem, r in sorted(results.items()):
        print(f"{stem}: {r}")
    if any("failed" in r for r in results.values()):
        raise SystemExit(1)

def _verify(stem):
    from . import driver
    problems = driver.verify_photo(stem)
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print("verify: clean")

def main(argv=None):
    ns = build_parser().parse_args(argv)
    return ns.fn(ns)

if __name__ == "__main__":
    raise SystemExit(main())
```

Exit statuses: 0 success, 1 any failure (printed to stderr). Direct `render`/`verify` calls do not check state preconditions (operator tools); `run` is the state-respecting path.

- [ ] **Step 1: Write the failing test** — rev 1's three driver tests (with the autouse `toolchain.verify` monkeypatch returning `[]`) plus:

```python
def test_verify_tool_drift_demotes_to_rendered(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "verified")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(toolchain, "verify",
                        lambda p: [{"name": "qpdf", "problem": "hash mismatch"}])
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "verify_photo", lambda s: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda s: None)
    driver.process_all()
    assert manifest.load()["photos"]["P1"]["state"] == "verified"  # re-verified

def test_render_tool_drift_hard_stops(tmp_repo, monkeypatch):
    monkeypatch.setattr(toolchain, "verify",
                        lambda p: [{"name": "rawtherapee", "problem": "hash mismatch"}])
    with pytest.raises(RuntimeError):
        driver.process_all()

def test_approve_requires_expression_audit(tmp_repo, monkeypatch):
    from pipeline import recipe
    rec = recipe.new("P1", "raw", 5776, 4336)
    recipe.save("P1", rec)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    with pytest.raises(RuntimeError):
        driver.approve("P1")
```

- [ ] **Step 2: FAIL. Step 3: Implement** `driver.py` per the interfaces above (rev 1 `render_photo`/`process_all` as the base, with: archive re-hash guard, `only=` selective render, denoise extra profile, strip-before-wrap ordering — strip all TIFs/JPGs FIRST, then build all PDFs, then the comparison sheet from the stripped natural/filmic/bw native JPGs).

- [ ] **Step 4: PASS full suite. Step 5: Commit.**

### Task 16: End-to-end + operator runbook

As rev 1 Task 16 with these runbook changes (write `docs/superpowers/review-loop.md` with the full rev 1 content, amended):

- Step 6 (crops) happens BEFORE approval, using `scripts/process.sh croppreview <stem> <style> <crop>` — Read the crop preview, adjust the recipe's normalized window if heads/hands are clipped or content sits inside the 2 % safe edge, re-preview, only then approve.
- Step 5 (expression audit) is mandatory — `approve` refuses an empty `expression_audit`; when multiple frames of the same grouping exist in a delivery, add a ranking note to each recipe ("strongest frame of this grouping: <stem>") per the spec's ranking requirement.
- Add Step 9: if a photo ever gets manual Photoshop/Topaz work, save the raster to `archive/`, record `{file, sha256}` in the recipe's `manual_assets`, and note the photo is outside automated re-render from that point.

End state: both photos `verified`; `Output/photos/<stem>/current/` has exactly 22 files + provenance.json; JPG view shows 9 links per photo; full pytest suite green.

---

## Self-Review Notes (rev 2)

- All 14 Codex findings addressed: (1) artifact records persisted + `stale_artifacts` + selective render + verify-tool demotion; (2) `manifest.rebuild` from recipes + provenance, provenance carries deps/raw/toolchain; (3) RT_SETTINGS/RT_CACHE, `lfauto`, ChannelMixer, Version=352, HL A/B in Checkpoint 1, PATH-fallback `paths.rt_cli()`; (4) lock adds font + rt_icc + pdfinfo, generated in Task 9 after assets exist; (5) archive re-hash guard implemented, double-render test explicitly descoped per spec scope boundaries; (6) publish allowlist + QA scratch in `run/qa-*`; (7) TIF cap exemption, compression check, dims from recipe, both resolution axes, unexpected-file check; (8) metadata strip/assert on TIFs, PDF doc-info check, strip-preserves and keep_capture_date=False tests; (9) preflight error wrapping, content-hash param used, archive overwrite guard, failure-isolation test; (10) normalized crop windows, ppi-aware validation, `croppreview` before approval, filename QA, denoise wired, RT sharpening removed; (11) two-step montage with pinned font + exact-canvas test; (12) stale-pid lock, provenance-based repoint recovery, views through `current`, rebuilt on startup; (13) `manual_assets` schema + runbook step, denoise override wired, audit-required approval, ranking note; (14) full argparse code with exit statuses, structured `toolchain.verify`, `croppreview` exists.
- Remaining intentional simplifications, justified by spec descopes: selective re-render granularity is per-artifact for crops/JPGs/PDFs but a stale TIF re-renders that style's full chain (a TIF change invalidates everything downstream anyway); no lab `submission_format`/`embed_icc` runtime branching (generic-v1 values are the only implemented path; a future lab profile with different values fails loudly at `labprofile.load` if fields are absent — adding branches is future work when a real lab profile arrives).
```
