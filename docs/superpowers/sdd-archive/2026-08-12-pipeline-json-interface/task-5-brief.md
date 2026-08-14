### Task 5: `driver.preview_photo` — atomic targeted preview with dims + provenance

**Files:**
- Modify: `pipeline/driver.py` (new function after `_record_render_dims`, ~line 86), `pipeline/driver.py:473-479` (`process_all` ingested branch), `pipeline/__main__.py:19-20` (`preview` subcommand)
- Test: `tests/test_driver.py` (additions)

**Interfaces:**
- Consumes: `render.rt_render`, `render.resolve_raw`, `provenance.record_preview`, `_dims`, `_record_render_dims`.
- Produces: `driver.preview_photo(stem, style) -> Path`, in this exact order. Failure contract: any failure through step 6's `recipe.save` leaves the previous preview AND recipe untouched; the one remaining window (crash/failure between the save and the final `os.replace`) degrades to a *stale-flagged* state — recorded hash ≠ on-disk preview, so `stale_styles` reports it — and can never read as falsely fresh:
  1. load `rec`; **verify the RAW**: `_sha256(render.resolve_raw(stem)) == rec["raw_sha256"]` else `RuntimeError` (same message pattern as `render_photo`, driver.py:207-211);
  2. **capture the pre-render input snapshot**: `material = provenance.gather_material(stem)`; `inputs_hash = provenance.style_input_hash(stem, style, rec, material)` — computed BEFORE rendering so an edit landing mid-render produces a mismatch on the next staleness check instead of being certified;
  3. render to `paths.run_dir()/f"preview-{stem}-{style}.tmp.jpg"` via `render.rt_render(raw, style, tmp, "jpg", 92, extra_profiles=(render.denoise_profile(),) if rec["overrides"].get("denoise") else ())` — same denoise handling as `render_photo`, or the inputs hash (which covers `overrides`) would describe profiles that weren't applied;
  4. **post-render input re-check**: recompute `provenance.style_input_hash(stem, style, rec, provenance.gather_material(stem))` and compare to the pre-render `inputs_hash` — mismatch (a profile edited mid-render) raises `RuntimeError("render inputs changed during preview render; re-run")` and discards the temp. This closes the render-from-live-files window without staging profile copies: a preview is only ever recorded when its inputs were identical before AND after the render.
  5. **validate the temp always** (whether or not dims are already recorded): `_dims(tmp)` with the ±16 guard against the declared dims; record dims into `rec` if not yet recorded;
  6. compose the full recipe update in memory (`provenance.record_preview(rec, stem, style, tmp, inputs_hash)`), then `recipe.save(stem, rec)` **before** `os.replace(tmp, final)` — if the save fails, the old JPG is still in place (reported failure = nothing changed); if a crash lands between save and replace, the recipe's content hash matches the temp, not `final`, so `stale_styles` flags the style and the state self-heals as stale rather than lying fresh.
- `process_all` ingested branch: replace `render.preview(stem, style)` with `preview_photo(stem, style)` (declared exception (b): batch previews now record provenance/dims keys).
- CLI `preview` keeps positional `stem style` (legacy, unchanged spelling) AND accepts the spec's flagged form: parser uses `p.add_argument("stem", nargs="?")`, `p.add_argument("style", nargs="?")`, `p.add_argument("--stem", dest="stem_flag")`, `p.add_argument("--style", dest="style_flag")`; handler resolves `stem = ns.stem_flag or ns.stem` (error `BAD_INPUT` if neither or both). **The flagged form is the JSON-mode canonical spelling** (`preview --stem S --style Y --json`) and is what Plan 2's `PipelineClient` sends; the positional form remains for humans and legacy scripts. Both route through `preview_photo`; still prints the output path in non-JSON mode.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_driver.py`)

```python
def _seed_preview_repo(tmp_repo, monkeypatch):
    """Styles + lock + lab profile + a REAL raw file whose hash matches the
    recipe (preview_photo verifies it — a fabricated hash fails)."""
    import hashlib as _hl
    import json as _json
    import pathlib, shutil as _sh
    from pipeline import recipe, toolchain
    from pipeline.paths import STYLES
    for s in STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    raw = tmp_repo / "Input/P1.RW2"
    raw.write_bytes(b"raw-bytes")
    recipe.save("P1", recipe.new(
        "P1", _hl.sha256(b"raw-bytes").hexdigest(), 5776, 4336))
    return raw


def test_preview_photo_atomic_and_records(tmp_repo, monkeypatch):
    from pipeline import driver, paths, provenance, recipe, render
    _seed_preview_repo(tmp_repo, monkeypatch)

    def fake_rt(raw, style, out, fmt, quality, extra_profiles=()):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"JPG:" + style.encode())
    monkeypatch.setattr(render, "rt_render", fake_rt)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))

    out = driver.preview_photo("P1", "natural")
    assert out == paths.previews_dir() / "P1_natural_preview.jpg"
    assert out.read_bytes() == b"JPG:natural"
    rec = recipe.load("P1")
    assert rec["render_width"] == 5784
    assert rec["previews"]["natural"]["content"] == provenance.content_hash(out)


def test_preview_photo_refuses_raw_hash_mismatch(tmp_repo, monkeypatch):
    from pipeline import driver, render
    raw = _seed_preview_repo(tmp_repo, monkeypatch)
    raw.write_bytes(b"DIFFERENT raw bytes")
    monkeypatch.setattr(render, "rt_render",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not render")))
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="hash mismatch"):
        driver.preview_photo("P1", "natural")


def test_preview_photo_failure_keeps_previous_jpg(tmp_repo, monkeypatch):
    from pipeline import driver, paths, render
    _seed_preview_repo(tmp_repo, monkeypatch)
    prior = paths.previews_dir() / "P1_natural_preview.jpg"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_bytes(b"OLD")

    def boom(raw, style, out, fmt, quality, extra_profiles=()):
        raise render.RenderError("rt exploded")
    monkeypatch.setattr(render, "rt_render", boom)

    import pytest as _pytest
    with _pytest.raises(render.RenderError):
        driver.preview_photo("P1", "natural")
    assert prior.read_bytes() == b"OLD"


def test_preview_photo_detects_mid_render_input_edit(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, render
    _seed_preview_repo(tmp_repo, monkeypatch)
    before = (tmp_repo / "recipes/P1.yaml").read_bytes()

    def rt_that_edits_inputs(raw, style, out, fmt, quality, extra_profiles=()):
        (paths.sidecars_dir() / "P1_natural.pp3").write_text(
            "[Exposure]\nCompensation=0.5\n")     # edit lands mid-render
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"JPG")
    monkeypatch.setattr(render, "rt_render", rt_that_edits_inputs)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))

    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="inputs changed"):
        driver.preview_photo("P1", "natural")
    assert (tmp_repo / "recipes/P1.yaml").read_bytes() == before
    assert not (paths.previews_dir() / "P1_natural_preview.jpg").exists()
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_driver.py -q -k preview_photo` → FAIL (`preview_photo` missing).

- [ ] **Step 3: Implement** — add to `pipeline/driver.py` (imports: `os`, `provenance` added to the package import list):

```python
def preview_photo(stem, style):
    if style not in paths.STYLES:
        raise ValueError(f"unknown style: {style}")
    rec = recipe.load(stem)
    raw = render.resolve_raw(stem)
    actual_hash = _sha256(raw)
    if actual_hash != rec["raw_sha256"]:
        raise RuntimeError(
            f"archived RAW hash mismatch for {stem}: "
            f"expected {rec['raw_sha256']}, got {actual_hash}")
    material = provenance.gather_material(stem)
    inputs_hash = provenance.style_input_hash(stem, style, rec, material)

    final = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
    tmp = paths.run_dir() / f"preview-{stem}-{style}.tmp.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.unlink(missing_ok=True)
    extra = ((render.denoise_profile(),)
             if rec["overrides"].get("denoise") else ())
    render.rt_render(raw, style, tmp, "jpg", 92, extra_profiles=extra)

    # Inputs must be identical before AND after the render, or the recorded
    # provenance would describe profiles that weren't the ones rendered.
    post_hash = provenance.style_input_hash(
        stem, style, rec, provenance.gather_material(stem))
    if post_hash != inputs_hash:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"render inputs changed during preview render for {stem} "
            f"[{style}]; re-run")

    # Validate the temp ALWAYS; a failure here leaves preview + recipe alone.
    width, height = _dims(tmp)
    if (abs(width - int(rec["width"])) > 16
            or abs(height - int(rec["height"])) > 16):
        raise RuntimeError(
            f"render dimensions {width}x{height} differ from declared "
            f"{rec['width']}x{rec['height']} by more than 16 pixels")
    try:
        _render_dims(rec)
    except ValueError:
        rec["render_width"], rec["render_height"] = width, height
    provenance.record_preview(rec, stem, style, tmp, inputs_hash)

    # Recipe first, swap second: a save failure changes nothing on disk; a
    # crash between the two leaves a hash mismatch that reads as STALE, not
    # as falsely fresh.
    recipe.save(stem, rec)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, final)
    return final
```

(Recorded content hash is of the temp bytes — byte-identical to `final` after `os.replace`. Additional tests: `overrides["denoise"] = True` → the fake `rt_render` receives one extra profile; a `_dims` failure on the temp leaves the previous preview file and recipe bytes unchanged; a sidecar mutated inside the fake `rt_render` (simulating a mid-render edit) → `RuntimeError` mentioning "inputs changed" and no recipe/preview change.)

In `process_all` (driver.py:475-476), replace `render.preview(stem, style)` with `preview_photo(stem, style)`. In `__main__.py:20`, the `preview` handler resolves the positional/flag pair first — `stem = ns.stem_flag or ns.stem; style = ns.style_flag or ns.style` (error `BAD_INPUT`/usage if a value is missing or given both ways) — then `print(driver.preview_photo(stem, style))` (import stays lazy via the existing `from . import driver`).

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_driver.py -q` → PASS. If any existing preview-path test asserts `render.preview` is called from `process_all`, update it here explicitly (declared exception (b)) and note the update in the commit message.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/driver.py pipeline/__main__.py tests/test_driver.py
git commit -m "feat(pipeline): atomic targeted preview with dims + provenance recording"
```

---

