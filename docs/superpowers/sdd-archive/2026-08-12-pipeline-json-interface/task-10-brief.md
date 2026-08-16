### Task 10: `approve --review-file`

**Files:**
- Modify: `pipeline/driver.py` (new `approve_review` above `approve`), `pipeline/__main__.py` (`approve` gains `--review-file`, `--json`)
- Test: `tests/test_driver.py` (additions)

**Interfaces:**
- Consumes: `provenance.review_revision/stale_styles`, `geometry.validate_crop`, `recipe.fingerprint` path via `_current_fingerprint`-equivalent computed **from the already-loaded rec** (single-snapshot rule).
- Produces: `driver.approve_review(stem, review: dict) -> dict` — result `{"stem", "state": "approved", "fingerprint"}`.
  - Review dict: `expression_audit` (non-empty list of strings, else `BAD_INPUT`), `crops` (both of `paths.CROPS` required, else `BAD_INPUT`), optional `expected_review_revision`.
  - **Single snapshot:** load `rec` once; compute `provenance.review_revision(stem, rec)`; when `expected_review_revision` present and different → `CommandError("STALE_REVIEW", …)`; when present, also require `provenance.stale_styles(stem, rec) == []` → else `STALE_REVIEW` listing the styles. When absent (CLI path), skip both gates (spec §4.2 compatibility scoping).
  - Validate both windows with `geometry.validate_crop(window, width, height, crop, landscape, lab["ppi"])` using `_render_dims(rec)` — any failure → `BAD_INPUT`, nothing persisted.
  - Then: set `rec["crops"]`, `rec["expression_audit"]`, compute the fingerprint from **this same `rec` object** (`recipe.fingerprint(stem, rec, render.style_hashes(stem), render.seed_hash(), _lock(), _lab())`), set `rec["approval"]`, one `recipe.save`, then the manifest update exactly as `approve()` does (driver.py:396-399).
  - Existing `approve(stem)` is untouched.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_driver.py`)

```python
def _seed_approvable(tmp_repo, monkeypatch):
    import json as _json
    from pipeline import paths, recipe, toolchain
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    rec = recipe.new("P1", "aa" * 32, 5776, 4336)
    rec["render_width"], rec["render_height"] = 5784, 4344
    recipe.save("P1", rec)
    return {
        "expression_audit": ["eyes open — all: pass"],
        "crops": {
            "8x10": {"x": 0.075, "y": 0.0, "w": 0.85, "h": 1.0},
            "5x7": {"x": 0.0, "y": 0.036, "w": 1.0, "h": 0.928},
        },
    }


def test_approve_review_happy_path(tmp_repo, monkeypatch):
    from pipeline import driver, manifest, recipe
    review = _seed_approvable(tmp_repo, monkeypatch)
    result = driver.approve_review("P1", review)
    assert result["state"] == "approved"
    rec = recipe.load("P1")
    assert rec["approval"]["fingerprint"] == result["fingerprint"]
    assert rec["crops"]["8x10"]["w"] == 0.85
    m = manifest.load_readonly()
    assert m["photos"]["P1"]["state"] == "approved"


def test_approve_review_stale_revision_changes_nothing(tmp_repo, monkeypatch):
    from pipeline import driver, jsonio, recipe
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["expected_review_revision"] = "sha256:not-the-current-one"
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "STALE_REVIEW"
    assert recipe.load("P1")["approval"]["fingerprint"] is None


def test_approve_review_requires_both_crops_and_audit(tmp_repo, monkeypatch):
    from pipeline import driver, jsonio
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    del review["crops"]["5x7"]
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["expression_audit"] = []
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"


def test_approve_review_with_matching_revision_requires_fresh_previews(
        tmp_repo, monkeypatch):
    from pipeline import driver, jsonio, provenance, recipe
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    rec = recipe.load("P1")
    review["expected_review_revision"] = provenance.review_revision("P1", rec)
    # No previews rendered → every style is stale → STALE_REVIEW
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "STALE_REVIEW"
```

- [ ] **Step 2: Run to verify failure** — `-k approve_review` → FAIL.

- [ ] **Step 3: Implement** in `pipeline/driver.py`:

```python
def approve_review(stem, review):
    audit = review.get("expression_audit")
    if not audit or not all(isinstance(item, str) for item in audit):
        raise jsonio.CommandError(
            "BAD_INPUT", "expression_audit must be a non-empty list of strings")
    windows = review.get("crops") or {}
    missing = [c for c in paths.CROPS if c not in windows]
    if missing:
        raise jsonio.CommandError(
            "BAD_INPUT", f"crops missing windows: {missing}")

    # THE single snapshot: one recipe load + one material gather; revision,
    # staleness, and the final fingerprint all derive from these same reads,
    # so an edit between "check" and "persist" cannot enter the fingerprint
    # without having entered the checked revision.
    rec = recipe.load(stem)
    material = provenance.gather_material(stem)
    expected = review.get("expected_review_revision")
    if expected is not None:
        current = provenance.review_revision(stem, rec, material)
        if expected != current:
            raise jsonio.CommandError(
                "STALE_REVIEW",
                "review inputs changed since the reviewed snapshot")
        stale = provenance.stale_styles(stem, rec, material)
        if stale:
            raise jsonio.CommandError(
                "STALE_REVIEW", f"previews stale for styles: {stale}")

    try:
        width, height = _render_dims(rec)
    except ValueError as error:
        raise jsonio.CommandError("BAD_INPUT", str(error)) from error
    landscape = width >= height
    lab = material["lab"]
    for crop, window in windows.items():
        try:
            geometry.validate_crop(window, width, height, crop, landscape,
                                   lab["ppi"])
        except Exception as error:
            raise jsonio.CommandError(
                "BAD_INPUT", f"invalid {crop} window: {error}") from error

    rec["crops"] = {c: dict(windows[c]) for c in paths.CROPS}
    rec["expression_audit"] = list(audit)
    fingerprint = recipe.fingerprint(stem, rec, material["style_hashes"],
                                     material["seed_hash"], material["lock"],
                                     material["lab"])
    rec["approval"] = {
        "fingerprint": fingerprint,
        "approved_at": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
    }
    recipe.save(stem, rec)
    data = manifest.load()
    manifest.set_state(data, stem, "approved")
    data["photos"][stem]["fingerprint"] = fingerprint
    manifest.save(data)
    return {"stem": stem, "state": "approved", "fingerprint": fingerprint}
```

Strip the `source` key from submitted windows if present before validation (`window = {k: v for k, v in window.items() if k in ("x", "y", "w", "h")}`) — the app echoes `crops`-command windows back. `__main__.py`: `approve` keeps positional `stem` and additionally accepts `--stem` (same nargs-`?` + flag resolution as `preview`, Task 5); gains `--review-file` (path) and `--json`. The JSON-mode canonical spelling is `approve --stem S --review-file P --json` (what Plan 2 sends). With `--review-file`, handler reads the JSON file and calls `approve_review`; without it, legacy `driver.approve(stem)` untouched.

- [ ] **Step 4: Run to verify pass**, **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/driver.py pipeline/__main__.py tests/test_driver.py
git commit -m "feat(pipeline): approve --review-file with STALE_REVIEW gates"
```

---

