### Task 9: `crops` command

**Files:**
- Modify: `pipeline/__main__.py` (new read-only subcommand), `pipeline/driver.py` (new `crop_windows` function near `approve`)
- Test: `tests/test_driver.py` (additions)

**Interfaces:**
- Consumes: `subject.group_bbox_detail`, `geometry.centered_crop_norm/subject_crop_norm`, `_render_dims`.
- Produces: `driver.crop_windows(stem) -> dict` — spec §4.3 `crops` result:
  - Persisted windows (recipe `crops` values non-None) → `source: "persisted"`. `basis` describes only the *suggestion* path and stays within the spec's approved set (`faces | center | detector_error`); when **all** windows are persisted no suggestion runs and `basis` is `null` — persistence is communicated per-window by `source`, never by inventing a basis value.
  - Otherwise compute for the missing windows exactly as `approve` does (driver.py:350-384): needs `_render_dims` (else `CommandError("BAD_INPUT", "render dims not recorded; generate previews first")`); `group_bbox_detail` on the natural preview → basis `"faces"`, `"no_faces"` → centered windows + basis `"center"`, `"detector_error"` → centered + basis `"detector_error"`, missing natural preview → centered + basis `"center"`.
  - Never persists anything.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_driver.py`)

```python
def test_crop_windows_suggests_with_basis(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, subject
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    rec = recipe.load("P1")
    rec["render_width"], rec["render_height"] = 5784, 4344
    recipe.save("P1", rec)
    preview = paths.previews_dir() / "P1_natural_preview.jpg"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"x")
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda p: ({"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.3},
                                   "faces"))
    result = driver.crop_windows("P1")
    assert result["basis"] == "faces"
    assert set(result["windows"]) == set(paths.CROPS)
    assert all(w["source"] == "suggested" for w in result["windows"].values())
    before = recipe.load("P1")
    assert before["crops"] == {"8x10": None, "5x7": None}   # nothing persisted


def test_crop_windows_detector_error_falls_back_centered(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, subject
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    rec = recipe.load("P1")
    rec["render_width"], rec["render_height"] = 5784, 4344
    recipe.save("P1", rec)
    p = paths.previews_dir() / "P1_natural_preview.jpg"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda path: (None, "detector_error"))
    result = driver.crop_windows("P1")
    assert result["basis"] == "detector_error"


def test_crop_windows_requires_dims(tmp_repo):
    from pipeline import driver, jsonio, recipe
    import pytest as _pytest
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    with _pytest.raises(jsonio.CommandError) as e:
        driver.crop_windows("P1")
    assert e.value.code == "BAD_INPUT"
```

- [ ] **Step 2: Run to verify failure** — `-k crop_windows` → FAIL.

- [ ] **Step 3: Implement** in `pipeline/driver.py` (import `jsonio`):

```python
def crop_windows(stem):
    rec = recipe.load(stem)
    persisted = {c: w for c, w in rec["crops"].items() if w is not None}
    if len(persisted) == len(paths.CROPS):
        return {"stem": stem, "basis": None,
                "windows": {c: dict(w, source="persisted")
                            for c, w in persisted.items()}}
    try:
        width, height = _render_dims(rec)
    except ValueError as error:
        raise jsonio.CommandError(
            "BAD_INPUT", "render dims not recorded; generate previews first"
        ) from error
    landscape = width >= height
    preview = paths.previews_dir() / f"{stem}_natural_preview.jpg"
    if preview.is_file():
        bbox, basis = subject.group_bbox_detail(preview)
        if basis == "no_faces":
            basis = "center"
    else:
        bbox, basis = None, "center"
    windows = {}
    for crop in paths.CROPS:
        if crop in persisted:
            windows[crop] = dict(persisted[crop], source="persisted")
            continue
        if bbox is None:
            window = geometry.centered_crop_norm(width, height, crop, landscape)
        else:
            window = geometry.subject_crop_norm(width, height, crop,
                                                landscape, bbox)
        windows[crop] = dict(window, source="suggested")
    return {"stem": stem, "basis": basis, "windows": windows}
```

`__main__.py`: `crops` subcommand, non-mutating, `--stem` required, `--json` → `run_json(lambda: driver.crop_windows(ns.stem))`; legacy pretty-print via the `_locked_json`-style fallback (no lock).

- [ ] **Step 4: Run to verify pass**, **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/driver.py pipeline/__main__.py tests/test_driver.py
git commit -m "feat(pipeline): crops command — suggested/persisted windows with basis"
```

---

