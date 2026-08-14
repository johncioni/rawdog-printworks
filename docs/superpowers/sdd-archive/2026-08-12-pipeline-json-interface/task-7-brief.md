### Task 7: `adjust` command

**Files:**
- Create: `pipeline/adjust.py`
- Modify: `pipeline/__main__.py` (new subcommand)
- Test: `tests/test_adjust.py`

**Interfaces:**
- Consumes: `pp3.Pp3`, `provenance.review_revision/record_preview`, `driver.preview_photo`, `recipe.load/save`, `jsonio.CommandError`.
- Produces: `adjust.apply(stem, style, temperature=None, exposure=None, reset=False) -> dict` returning the spec §4.3 `adjust` result (`stem`, `style`, `preview` repo-relative, `temperature`/`exposure` as `{"value", "source"}` post-merge, `review_revision_before`, `review_revision_after`).
- Ownership model (spec §4.2): `rec["app_adjustments"][style]` maps control name → `{"previous": {key: value|None…}, "last_written": {key: value…}}`. Controls: `"wb"` bundles `Setting`/`Temperature`/`Green` in `[White Balance]`; `"exposure"` is `Compensation` in `[Exposure]`. `previous` captures each key's pre-app value (`None` = key absent) on **first** app write only. Reset restores a control only when every current key equals `last_written`; otherwise leaves the pp3 untouched and drops the ownership entry. Write order: sidecar first (`write_atomic`), recipe second.
- Validation: `temperature` int in [3000, 9000]; `exposure` float in [-1.0, 1.0]; else `CommandError("BAD_INPUT", …)`. Unknown stem → `NOT_FOUND` (recipe file missing). `reset` with `temperature`/`exposure` → `BAD_INPUT`.
- After a non-reset write (and after a reset that changed the file): call `driver.preview_photo(stem, style)`; a `render.RenderError` becomes `CommandError("RENDER_FAILED", str(e))` — the sidecar keeps the user's values (spec §7).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_adjust.py
import json

import pytest

from pipeline import adjust, jsonio, paths, pp3, recipe, toolchain


@pytest.fixture
def repo(tmp_repo, monkeypatch):
    from pipeline import driver
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    calls = []

    def fake_preview(stem, style):
        calls.append((stem, style))
        p = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"render-{len(calls)}".encode())
        return p
    monkeypatch.setattr(driver, "preview_photo", fake_preview)
    return calls


def test_adjust_writes_wb_bundle_and_ownership(repo):
    result = adjust.apply("P1", "natural", temperature=5600)
    side = pp3.Pp3.load(paths.sidecars_dir() / "P1_natural.pp3")
    assert side.get("White Balance", "Setting") == "Custom"
    assert side.get("White Balance", "Temperature") == "5600"
    assert side.get("White Balance", "Green") == "1.0"
    rec = recipe.load("P1")
    own = rec["app_adjustments"]["natural"]["wb"]
    assert own["previous"] == {"Setting": None, "Temperature": None,
                               "Green": None}
    assert own["last_written"] == {"Setting": "Custom", "Temperature": "5600",
                                   "Green": "1.0"}
    assert result["temperature"] == {"value": 5600, "source": "sidecar"}
    assert result["review_revision_before"] != result["review_revision_after"]


def test_adjust_preserves_hand_written_keys(repo):
    hand = paths.sidecars_dir() / "P1_bw.pp3"
    hand.write_text("# hand note\n[Exposure]\nCompensation=0.15\n"
                    "CurveMode=Standard\n")
    adjust.apply("P1", "bw", exposure=0.30)
    text = hand.read_text()
    assert "# hand note" in text and "CurveMode=Standard" in text
    assert "Compensation=0.3" in text
    own = recipe.load("P1")["app_adjustments"]["bw"]["exposure"]
    assert own["previous"] == {"Compensation": "0.15"}   # captured pre-app value


def test_reset_restores_previous_and_skips_diverged(repo):
    adjust.apply("P1", "natural", temperature=5600)
    adjust.apply("P1", "natural", reset=True)
    side = pp3.Pp3.load(paths.sidecars_dir() / "P1_natural.pp3")
    assert side.get("White Balance", "Temperature") is None   # restored to absent

    adjust.apply("P1", "vibrant", temperature=5600)
    # hand edit after app write → diverged
    p = paths.sidecars_dir() / "P1_vibrant.pp3"
    doc = pp3.Pp3.load(p); doc.set("White Balance", "Temperature", "4800")
    doc.write_atomic(p)
    adjust.apply("P1", "vibrant", reset=True)
    assert pp3.Pp3.load(p).get("White Balance", "Temperature") == "4800"
    # Ownership drop is PERSISTED even though the reset touched no sidecar
    assert "wb" not in recipe.load("P1")["app_adjustments"].get("vibrant", {})


def test_adjust_after_divergence_recaptures_previous(repo):
    # App writes, hand edits, app writes again: the new `previous` must be
    # the HAND-EDITED value, so a later reset restores the hand edit.
    adjust.apply("P1", "filmic", temperature=5600)
    p = paths.sidecars_dir() / "P1_filmic.pp3"
    doc = pp3.Pp3.load(p); doc.set("White Balance", "Temperature", "4800")
    doc.write_atomic(p)
    adjust.apply("P1", "filmic", temperature=5200)   # reconcile → re-own
    own = recipe.load("P1")["app_adjustments"]["filmic"]["wb"]
    assert own["previous"]["Temperature"] == "4800"
    adjust.apply("P1", "filmic", reset=True)
    assert pp3.Pp3.load(p).get("White Balance", "Temperature") == "4800"


def test_adjust_validation(repo):
    with pytest.raises(jsonio.CommandError) as e:
        adjust.apply("P1", "natural", temperature=12000)
    assert e.value.code == "BAD_INPUT"
    with pytest.raises(jsonio.CommandError) as e:
        adjust.apply("NOPE", "natural", temperature=5000)
    assert e.value.code == "NOT_FOUND"


def test_adjust_render_failure_keeps_sidecar(repo, monkeypatch):
    from pipeline import driver, render

    def boom(stem, style):
        raise render.RenderError("rt failed")
    monkeypatch.setattr(driver, "preview_photo", boom)
    with pytest.raises(jsonio.CommandError) as e:
        adjust.apply("P1", "filmic", exposure=-0.2)
    assert e.value.code == "RENDER_FAILED"
    assert pp3.Pp3.load(paths.sidecars_dir() / "P1_filmic.pp3").get(
        "Exposure", "Compensation") == "-0.2"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_adjust.py -q` → FAIL.

- [ ] **Step 3: Implement `pipeline/adjust.py`**

```python
from . import jsonio, paths, pp3, provenance, recipe, render

_WB_KEYS = ("Setting", "Temperature", "Green")
_CONTROLS = {
    "wb": ("White Balance", _WB_KEYS),
    "exposure": ("Exposure", ("Compensation",)),
}


def _load_recipe(stem):
    try:
        return recipe.load(stem)
    except FileNotFoundError as error:
        raise jsonio.CommandError("NOT_FOUND", f"unknown stem: {stem}") from error


def _validate(style, temperature, exposure, reset):
    if style not in paths.STYLES:
        raise jsonio.CommandError("BAD_INPUT", f"unknown style: {style}")
    if reset and (temperature is not None or exposure is not None):
        raise jsonio.CommandError("BAD_INPUT", "--reset takes no values")
    if not reset and temperature is None and exposure is None:
        raise jsonio.CommandError("BAD_INPUT", "nothing to adjust")
    if temperature is not None and not 3000 <= int(temperature) <= 9000:
        raise jsonio.CommandError("BAD_INPUT", "temperature out of range 3000-9000")
    if exposure is not None and not -1.0 <= float(exposure) <= 1.0:
        raise jsonio.CommandError("BAD_INPUT", "exposure out of range -1.0..1.0")


def _capture_previous(doc, section, keys):
    return {k: doc.get(section, k) for k in keys}


def _own(rec, style):
    return rec.setdefault("app_adjustments", {}).setdefault(style, {})


def _reconcile(rec, style, doc):
    """Drop ownership of any bundle whose current pp3 values diverged from
    last_written (a hand edit — or a crash between sidecar and recipe writes
    — happened since the app wrote). Runs before EVERY operation, so a later
    app write re-captures `previous` from the hand-edited state instead of
    silently overwriting it, and reset can never touch a diverged bundle.
    Returns True if any ownership entry was dropped (recipe needs saving)."""
    dropped = False
    ownership = (rec.get("app_adjustments") or {}).get(style) or {}
    for control in list(ownership):
        section, keys = _CONTROLS[control]
        current = _capture_previous(doc, section, keys)
        if current != ownership[control].get("last_written"):
            del rec["app_adjustments"][style][control]
            dropped = True
    return dropped


def _write_control(rec, style, doc, control, values):
    section, keys = _CONTROLS[control]
    ownership = _own(rec, style)
    if control not in ownership:
        ownership[control] = {"previous": _capture_previous(doc, section, keys)}
    for key in keys:
        doc.set(section, key, values[key])
    ownership[control]["last_written"] = dict(values)


def _reset_control(rec, style, doc, control):
    # _reconcile already removed diverged bundles; anything still owned is
    # exactly as the app last wrote it and is safe to restore.
    section, keys = _CONTROLS[control]
    entry = _own(rec, style).get(control)
    if entry is None:
        return False
    for key in keys:
        prior = entry["previous"].get(key)
        if prior is None:
            doc.remove(section, key)
        else:
            doc.set(section, key, prior)
    doc.remove_section_if_empty(section)   # no stranded [White Balance] headers
    del rec["app_adjustments"][style][control]
    return True


def _semantically_empty(doc):
    # Only a TRULY empty document qualifies — a comment-only sidecar (e.g.
    # from render.ensure_sidecar) is "something else remaining": deleting it
    # would change style_hashes (sidecar existence feeds the fingerprint).
    return doc.dump().strip() == ""


def apply(stem, style, temperature=None, exposure=None, reset=False):
    _validate(style, temperature, exposure, reset)
    rec = _load_recipe(stem)
    revision_before = provenance.review_revision(stem, rec)
    side_path = paths.sidecars_dir() / f"{stem}_{style}.pp3"
    doc = pp3.Pp3.load(side_path)
    recipe_dirty = _reconcile(rec, style, doc)     # spec §4.2 crash reconcile
    sidecar_dirty = False
    if reset:
        for control in _CONTROLS:
            if _reset_control(rec, style, doc, control):
                sidecar_dirty = recipe_dirty = True
    else:
        if temperature is not None:
            _write_control(rec, style, doc, "wb", {
                "Setting": "Custom",
                "Temperature": str(int(temperature)),
                "Green": "1.0",
            })
            sidecar_dirty = recipe_dirty = True
        if exposure is not None:
            _write_control(rec, style, doc, "exposure",
                           {"Compensation": f"{float(exposure):g}"})
            sidecar_dirty = recipe_dirty = True
    if sidecar_dirty:
        if side_path.exists() and _semantically_empty(doc):
            side_path.unlink()           # spec: "and the file if nothing else remains"
        else:
            doc.write_atomic(side_path)  # sidecar first…
    if recipe_dirty:
        recipe.save(stem, rec)           # …recipe second (spec §4.2 crash rule)
    if sidecar_dirty:
        from . import driver
        try:
            driver.preview_photo(stem, style)
        except render.RenderError as error:
            raise jsonio.CommandError("RENDER_FAILED", str(error)) from error
        rec = recipe.load(stem)
    from . import status as status_mod
    result = {
        "stem": stem,
        "style": style,
        "preview": f"previews/{stem}_{style}_preview.jpg",
        "temperature": status_mod._control(stem, style, "White Balance",
                                           "Temperature", int),
        "exposure": status_mod._control(stem, style, "Exposure",
                                        "Compensation", float),
        "review_revision_before": revision_before,
        "review_revision_after": provenance.review_revision(stem, rec),
    }
    return result
```

`pipeline/__main__.py` addition:

```python
from . import adjust as adjust_mod  # inside build_parser's lazy import block

p = sub.add_parser("adjust")
p.add_argument("--stem", required=True); p.add_argument("--style", required=True)
p.add_argument("--temperature", type=int); p.add_argument("--exposure", type=float)
p.add_argument("--reset", action="store_true"); p.add_argument("--json", action="store_true")
p.set_defaults(fn=lambda ns: _locked_json(ns, lambda: adjust_mod.apply(
    ns.stem, ns.style, ns.temperature, ns.exposure, ns.reset)))
```

Define `_locked_json` in THIS task inside `__main__.py` (Task 8 later generalizes dispatch; it must keep this helper's behavior):

```python
def _locked_json(ns, fn):
    from . import jsonio, publish
    def body():
        with publish.acquire_lock():
            return fn()
    if getattr(ns, "json", False):
        return jsonio.run_json(body)
    result = body()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
```

(`import json` at top of `__main__.py`.) `adjust` without `--json` is a new command, so pretty-printing its result is not a compatibility concern.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_adjust.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/adjust.py pipeline/__main__.py tests/test_adjust.py
git commit -m "feat(pipeline): adjust command — locked sidecar merge with ownership tracking"
```

---

