### Task 6: `status --json`

**Files:**
- Create: `pipeline/status.py`
- Modify: `pipeline/__main__.py:17` (status subcommand gains `--json`), `pipeline/publish.py` (add `lock_status()` helper after `_lock_is_stale`, ~line 33), `pipeline/subject.py` (no — not needed here)
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: `manifest.load_readonly`, `manifest.effective_state`, `provenance.*`, `recipe.load`, `toolchain.verify`, `publish.lock_status`.
- Produces:
  - `publish.lock_status() -> dict` — `{"held": bool, "stale": bool, "pid": int|None}`; a lock whose PID is dead reports `held: False, stale: True` (never deletes the file).
  - `status.snapshot() -> dict` — exactly the spec §4.3 `status` result. Per photo: `stem`, `state` (via `effective_state` with the current fingerprint), `delivery_id`/`ingested_at` (recipe keys or `None`), `review_revision`, `previews` (repo-relative path per style where the file exists, else `None`), `preview_hashes` (per existing style file, else `None`), `stale_previews`, `adjustments` (per style, per control `{"value", "source"}` — source resolution below), `crops` (persisted windows only, `{}` when all None), `expression_audit`, `published` (`{"version": "vNNN", "path": "Output/photos/<stem>/current", "artifact_count": N}` from the `current` symlink target name + `provenance.json` artifact count, or all-`None`).
  - Adjustment source resolution (per control): sidecar `sidecars/{stem}_{style}.pp3` has the key → `"sidecar"`; else base `config/styles/{style}.pp3` has it → `"style"`; else → `"camera"` (temperature) / `"style"` with value `None` (exposure follows the same chain; when neither file pins it, source `"camera"`, value `None`). Values via `Pp3.get`: `Temperature` from `[White Balance]` (int), `Compensation` from `[Exposure]` (float).
  - Snapshot coherence: collect `(path, mtime_ns)` of every recipe read; after assembly re-stat and retry the whole build **once** after 0.1 s if any moved.
  - `toolchain` field: `{"ok": problems == [], "failures": problems}` from `toolchain.verify(config_dir()/"toolchain.lock")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_status.py
import json

import pytest

from pipeline import manifest, paths, recipe, status, toolchain


@pytest.fixture
def repo(tmp_repo, monkeypatch):
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/styles/filmic.pp3").write_text(
        "[White Balance]\nSetting=Custom\nTemperature=5650\nGreen=1.0\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    monkeypatch.setattr(toolchain, "verify", lambda p: [])
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    return tmp_repo


def test_snapshot_empty_repo(repo):
    snap = status.snapshot()
    assert snap["photos"] == []
    assert snap["styles"] == list(paths.STYLES)
    assert snap["toolchain"] == {"ok": True, "failures": []}
    assert snap["lock"] == {"held": False, "stale": False, "pid": None}


def test_snapshot_photo_fields_and_no_writes(repo):
    rec = recipe.new("P1", "aa" * 32, 5776, 4336)
    rec["delivery_id"] = "uuid-1"
    rec["ingested_at"] = "2026-08-12T00:00:00.000000Z"
    recipe.save("P1", rec)
    m = {"photos": {"P1": {"state": "ingested", "fingerprint": None}}}
    manifest.save(m)
    before = {p: p.stat().st_mtime_ns for p in paths.root().rglob("*")
              if p.is_file()}

    snap = status.snapshot()

    after = {p: p.stat().st_mtime_ns for p in paths.root().rglob("*")
             if p.is_file()}
    assert before == after                       # side-effect-free
    (photo,) = snap["photos"]
    assert photo["stem"] == "P1"
    assert photo["state"] == "ingested"
    assert photo["delivery_id"] == "uuid-1"
    assert photo["review_revision"].startswith("sha256:")
    assert photo["stale_previews"] == sorted(paths.STYLES)
    assert photo["adjustments"]["filmic"]["temperature"] == {
        "value": 5650, "source": "style"}
    assert photo["adjustments"]["natural"]["temperature"] == {
        "value": None, "source": "camera"}
    assert photo["crops"] == {}
    assert photo["published"] == {"version": None, "path": None,
                                  "artifact_count": None}


def test_snapshot_reports_stale_lock(repo):
    lock = paths.run_dir() / "driver.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999")                    # dead PID
    snap = status.snapshot()
    assert snap["lock"] == {"held": False, "stale": True, "pid": 999999}
    assert lock.exists()                         # never deleted


def test_sidecar_exposure_only_reports_mixed_sources(repo):
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    manifest.save({"photos": {"P1": {"state": "ingested", "fingerprint": None}}})
    (paths.sidecars_dir() / "P1_bw.pp3").write_text(
        "[Exposure]\nCompensation=0.15\n")
    snap = status.snapshot()
    (photo,) = snap["photos"]
    assert photo["adjustments"]["bw"]["exposure"] == {
        "value": 0.15, "source": "sidecar"}
    assert photo["adjustments"]["bw"]["temperature"]["source"] == "camera"
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_status.py -q` → FAIL.

- [ ] **Step 3: Implement**

`pipeline/publish.py` addition:

```python
def lock_status():
    lock = paths.run_dir() / "driver.lock"
    if not lock.exists():
        return {"held": False, "stale": False, "pid": None}
    try:
        pid = int(lock.read_text().strip())
    except (OSError, ValueError):
        pid = None
    stale = _lock_is_stale(lock)
    return {"held": not stale, "stale": stale, "pid": pid}
```

`pipeline/status.py`:

```python
import time

from . import (manifest, paths, pp3, provenance, publish, recipe, toolchain)


def _rel(path):
    try:
        return str(path.relative_to(paths.root()))
    except ValueError:
        return str(path)


def _control(stem, style, section, key, cast):
    side = pp3.Pp3.load(paths.sidecars_dir() / f"{stem}_{style}.pp3")
    value = side.get(section, key)
    if value is not None:
        return {"value": cast(value), "source": "sidecar"}
    base = pp3.Pp3.load(paths.config_dir() / "styles" / f"{style}.pp3")
    value = base.get(section, key)
    if value is not None:
        return {"value": cast(value), "source": "style"}
    return {"value": None, "source": "camera"}


def _photo(stem, m):
    rec = recipe.load(stem)
    # One recipe load + one material gather per photo; the fingerprint is
    # computed from THIS rec, never a re-read (coherence with review_revision).
    material = provenance.gather_material(stem)
    fingerprint = recipe.fingerprint(
        stem, rec, material["style_hashes"], material["seed_hash"],
        material["lock"], material["lab"])
    previews, hashes = {}, {}
    for style in paths.STYLES:
        p = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
        # Existence derives from the SAME snapshot as the hashes — a fresh
        # p.exists() could disagree with them mid-mutation.
        hashes[style] = material["preview_hashes"][style]
        previews[style] = _rel(p) if hashes[style] is not None else None
    crops = {c: w for c, w in rec["crops"].items() if w is not None}
    published = {"version": None, "path": None, "artifact_count": None}
    current = paths.output_dir() / "photos" / stem / "current"
    if current.is_symlink():
        import json as _json
        prov = current / "provenance.json"
        published["version"] = current.resolve().name
        published["path"] = _rel(current)
        if prov.exists():
            published["artifact_count"] = len(
                _json.loads(prov.read_text()).get("artifacts", {}))
    return {
        "stem": stem,
        "state": manifest.effective_state(m, stem, fingerprint),
        "delivery_id": rec.get("delivery_id"),
        "ingested_at": rec.get("ingested_at"),
        "review_revision": provenance.review_revision(stem, rec, material),
        "previews": previews,
        "preview_hashes": hashes,
        "stale_previews": provenance.stale_styles(stem, rec, material),
        "adjustments": {
            style: {
                "temperature": _control(stem, style, "White Balance",
                                        "Temperature", int),
                "exposure": _control(stem, style, "Exposure",
                                     "Compensation", float),
            }
            for style in paths.STYLES
        },
        "crops": crops,
        "expression_audit": rec.get("expression_audit", []),
        "published": published,
    }


def _state_stamps():
    stamps = {p: p.stat().st_mtime_ns
              for p in paths.recipes_dir().glob("*.yaml")}
    m = paths.manifest_path()
    stamps[m] = m.stat().st_mtime_ns if m.exists() else None
    return stamps


def snapshot():
    for attempt in (0, 1):
        stamps = _state_stamps()
        m = manifest.load_readonly()
        problems = toolchain.verify(paths.config_dir() / "toolchain.lock")
        result = {
            "repo": str(paths.root()),
            "toolchain": {"ok": problems == [], "failures": problems},
            "lock": publish.lock_status(),
            "styles": list(paths.STYLES),
            "photos": [_photo(stem, m) for stem in sorted(m["photos"])],
        }
        if _state_stamps() == stamps or attempt == 1:
            return result
        time.sleep(0.1)
```

`pipeline/__main__.py`: `status` subparser gains `--json`; handler: `--json` → `return jsonio.run_json(lambda: status.snapshot())`; else legacy `_status()` exactly as today.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_status.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/status.py pipeline/publish.py pipeline/__main__.py tests/test_status.py
git commit -m "feat(pipeline): status --json snapshot (read-only, stale-lock aware)"
```

---

