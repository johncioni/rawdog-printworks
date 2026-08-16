### Task 12: `run --stem` / `--force` + progress events

**Files:**
- Modify: `pipeline/driver.py` (`process_all` signature; event emission in `process_all`, `render_photo`, `_finish_verified`), `pipeline/__main__.py` (`run` flags + JSON result)
- Test: `tests/test_driver.py` (additions)

**Interfaces:**
- Produces:
  - `driver.process_all(stems: set[str]|None = None, force: bool = False, collect: dict|None = None)` — `stems=None` is **exactly today's behavior** (legacy regression test below). `stems={"P1"}` limits the loop (`for stem in sorted(data["photos"]) if stems is None else sorted(stems & set(data["photos"]))`; a requested stem not in the manifest adds a `failed` entry `NOT_FOUND` to `collect`). `force=True`: for each selected stem in state `rendered`/`verified`, reset stored artifacts (`data["photos"][stem]["artifacts"] = {}`) and set state `approved` before the normal flow, so a full re-render happens (approval fingerprints untouched; `approved`-or-earlier states are unaffected by force).
  - `collect` (when provided) is filled with `{"published": [...], "advanced": [...], "failed": [...]}` — `published` appended in `_finish_verified` success path (`version` read from the `current` symlink after publish, `artifact_count` = `len(dependencies)`), `advanced` appended when the ingested branch completes previews, `failed` appended on verify failure (`VERIFY_FAILED`) or caught render error (`RENDER_FAILED`).
  - Events (all no-ops outside JSON mode): `process_all` emits `{"event": "stage", "stem", "stage"}` at the top of the ingested branch (`"preview"`), before `render_photo` (`"render"`), inside `_finish_verified` before verify (`"verify"`) and before `_publish_photo` (`"publish"`). `render_photo` emits `{"event": "progress", "stem", "stage": "render", "index": i, "total": len(requested), "detail": name}` (1-based, per artifact name as it is produced — emit after each raster/PDF lands in staging). `process_all` ingested branch emits per-style `{"event": "progress", "stem", "stage": "preview", "index": i, "total": len(paths.STYLES), "detail": style}`.
  - `run --json [--stem S] [--force]` result: the `collect` dict; `failed` non-empty → `CommandError("PARTIAL_FAILURE", f"{len(failed)} of {n} photos failed", result=collect)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_driver.py`)

```python
def test_process_all_stem_scoping(tmp_repo, monkeypatch):
    from pipeline import driver, manifest
    m = manifest.load()
    for stem in ("P1", "P2"):
        manifest.set_state(m, stem, "approved")
        m["photos"][stem]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    rendered = []
    monkeypatch.setattr(driver, "render_photo",
                        lambda stem, only=None: rendered.append(stem))
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    driver.process_all(stems={"P2"})
    assert rendered == ["P2"]


def test_process_all_force_rerenders_verified(tmp_repo, monkeypatch):
    from pipeline import driver, manifest
    m = manifest.load()
    manifest.set_state(m, "P1", "verified")
    m["photos"]["P1"]["fingerprint"] = "fp"
    m["photos"]["P1"]["artifacts"] = {"P1_natural.tif": {"x": 1}}
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    rendered = []
    monkeypatch.setattr(driver, "render_photo",
                        lambda stem, only=None: rendered.append((stem, only)))
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    driver.process_all(stems={"P1"}, force=True)
    assert rendered == [("P1", None)]            # full re-render, not stale-only


def test_process_all_collect_shapes(tmp_repo, monkeypatch):
    from pipeline import driver, manifest
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: ["bad pixels"])
    collect = {}
    driver.process_all(stems={"P1"}, collect=collect)
    assert collect["failed"][0]["stem"] == "P1"
    assert collect["failed"][0]["code"] == "VERIFY_FAILED"


def test_render_photo_emits_progress_in_json_mode(tmp_repo, monkeypatch):
    import json as _json
    from pipeline import crops, driver, jsonio, metadata, paths, pdfs, recipe, render
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    raw = tmp_repo / "Input/P1.RW2"
    raw.write_bytes(b"rawbytes")
    import hashlib as _hl
    rec = recipe.new("P1", _hl.sha256(b"rawbytes").hexdigest(), 5776, 4336)
    recipe.save("P1", rec)

    def fake_rt(raw_path, style, out, fmt, quality, extra_profiles=()):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"TIF")
    monkeypatch.setattr(render, "rt_render", fake_rt)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))
    monkeypatch.setattr(crops, "jpg_from_tif",
                        lambda tif, out, win, tgt, sh, q, ppi:
                        out.write_bytes(b"JPG"))
    monkeypatch.setattr(pdfs, "wrap",
                        lambda jpg, out, inches: out.write_bytes(b"PDF"))
    monkeypatch.setattr(pdfs, "comparison_sheet",
                        lambda stem, jpgs, staging:
                        (staging / f"{stem}_comparison.pdf").write_bytes(b"PDF"))
    monkeypatch.setattr(metadata, "strip",
                        lambda p, keep, ppi=None: None)

    events = []
    monkeypatch.setattr(jsonio, "emit", lambda e: events.append(e))
    driver.render_photo("P1")

    render_events = [e for e in events
                     if e.get("event") == "progress" and e["stage"] == "render"]
    assert render_events, "no render progress events emitted"
    assert render_events[0]["index"] == 1                 # 1-based
    assert all(e["stem"] == "P1" for e in render_events)
    assert all(e["total"] == render_events[0]["total"] for e in render_events)
    assert len(render_events) == render_events[0]["total"]
```

- [ ] **Step 2: Run to verify failure** — `-k "stem_scoping or force_rerenders or collect_shapes"` → FAIL (unexpected kwargs).

- [ ] **Step 3: Implement** — add the three keyword params with legacy-identical defaults; add the loop filter; thread `collect` appends and `jsonio.emit` calls at the named points. `_finish_verified(data, stem, collect=None)` gains the optional param. Two behaviors need explicit control flow, not threading:
  - **Per-stem failure isolation (collect mode only):** the existing loop body's `except RuntimeError` (driver.py:506-509) re-raises everything except manual-assets. When `collect is not None`, broaden it: `except (RuntimeError, render.RenderError) as error:` → manual-assets keeps its legacy skip-print; a verify failure already lands via `_finish_verified` (append `{"stem", "code": "VERIFY_FAILED", "message"}` there); anything else appends `{"stem", "code": "RENDER_FAILED", "message": str(error)}` and **continues to the next stem**. When `collect is None`, behavior is byte-for-byte legacy (re-raise) — the regression test from Step 4 pins this.
  - **Force preserves prior state on failure:** `force=True` resets `artifacts`/state **in the in-memory `data` only**, remembering each stem's prior `(state, artifacts)`; `manifest.save` for the forced downgrade happens only *after* that stem's successful `_finish_verified`. On failure, restore the remembered pair into `data` before continuing so the published tree and manifest still describe the last verified version.

  `__main__.py` `run`: `--stem`, `--force`, `--json`; JSON path builds `collect={}`, calls `process_all(stems={ns.stem} if ns.stem else None, force=ns.force, collect=collect)`, raises `CommandError("PARTIAL_FAILURE", f"{len(collect['failed'])} of {n} photos failed", result=collect)` when `collect["failed"]`; catches the toolchain-drift `RuntimeError` → `CommandError("TOOLCHAIN_FAILED", …)`; legacy path calls `process_all()` bare. Add a mixed-batch test: two approved stems, first renders and publishes, second's `verify_photo` returns problems → `collect["published"]` has one entry, `collect["failed"]` one `VERIFY_FAILED` entry, and the loop reached both stems. Add a force-failure test: forced verified stem whose render raises → manifest state and `artifacts` for that stem are unchanged from before the call.

- [ ] **Step 4: Legacy regression guard** — add and run:

```python
def test_process_all_no_args_matches_legacy_flow(tmp_repo, monkeypatch):
    # Same scenario as test_approved_photo_flows_to_verified but through the
    # new signature with no arguments — states and calls must be identical.
    from pipeline import driver, manifest
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    driver.process_all()
    assert manifest.load()["photos"]["P1"]["state"] == "verified"
```

Run: `.venv/bin/python -m pytest tests/test_driver.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/driver.py pipeline/__main__.py tests/test_driver.py
git commit -m "feat(pipeline): run --stem/--force, collect results, progress events"
```

---

