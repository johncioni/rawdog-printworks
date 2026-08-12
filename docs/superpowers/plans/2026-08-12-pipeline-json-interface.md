# Pipeline JSON Interface Implementation Plan (App Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the additive JSON command interface (spec §4.2–4.3 of `docs/superpowers/specs/2026-08-12-macos-app-design.md`) to the Python pipeline so the RAWdog Printworks app (Plan 2) can drive it; deliverable includes the golden contract fixtures.

**Architecture:** New focused modules (`jsonio`, `pp3`, `provenance`, `status`, `adjust`) plus additive extensions to `__main__.py`, `driver.py`, `ingest.py`, `render.py`, `recipe.py`, `manifest.py`. In `--json` mode stdout carries NDJSON only (legacy prints are redirected to stderr); the final line is always an envelope. Disk stays the single source of truth; every mutating command runs under the existing driver lock.

**Tech Stack:** Python 3 (repo `.venv`), pytest, PyYAML; no new dependencies.

## Global Constraints (from spec §2, binding on every task)

- Pipeline changes are **additive only**. All existing CLI invocations behave as today when the new flags are absent, with exactly two declared exceptions: (a) mutating commands gain lock acquisition; (b) preview-generating paths additionally record optional provenance/dimension fields in recipes (new keys only — no existing key's value changes, no state transition changes).
- The existing test suite (171 tests) keeps passing; any existing test updated for exception (b) is updated explicitly in a task step, never silently.
- Every mutating CLI entry point takes the driver lock; `status` and `crops` are read-only and lock-free. **Lock resolution (binding):** `run` keeps the existing lock inside `driver.process_all()` (driver.py:436) — dispatch does NOT wrap `run` (double-acquisition of the non-reentrant O_EXCL lock would deadlock). All other mutating commands (`ingest`, `preview`, `croppreview`, `approve`, `render`, `verify`, `adjust`) are wrapped in `publish.acquire_lock()` at dispatch in `__main__.py`, exactly once each.
- Exit code is 0 iff the final envelope says `ok: true`. Unhandled exceptions map to `INTERNAL`. Error codes: `LOCK_HELD`, `TOOLCHAIN_FAILED`, `RENDER_FAILED`, `VERIFY_FAILED`, `INVALID_STATE`, `STALE_REVIEW`, `PARTIAL_FAILURE`, `NOT_FOUND`, `BAD_INPUT`, `INTERNAL`.
- JSON-mode stdout discipline: at activation, the real stdout is saved for NDJSON; `sys.stdout` is redirected to `sys.stderr` so every legacy `print()` in driver/ingest internals lands on stderr with zero edits to those internals.
- `status` must be side-effect-free: it may not write any repo file (today `manifest.load()` → `rebuild()` → `save()` violates this; Task 2 fixes it).
- Paths in JSON output are repo-relative strings; crop windows are normalized [0,1] floats; timestamps are UTC RFC 3339.
- Run the full quality gate (`.venv/bin/python -m pytest tests/ -q`) before reporting any task complete.

## File Structure

| File | Responsibility |
|---|---|
| `pipeline/jsonio.py` (new) | JSON mode activation/stdout discipline, event emission, envelopes, `CommandError`, exception→code mapping |
| `pipeline/pp3.py` (new) | Line-preserving pp3 read/edit/write (comments and unknown keys survive round-trips) |
| `pipeline/provenance.py` (new) | Per-style input-material hash, preview provenance record/check, `review_revision`, content-hash cache |
| `pipeline/status.py` (new) | Read-only snapshot builder (spec §4.3 `status` result) |
| `pipeline/adjust.py` (new) | Slider backend: sidecar merge, ownership tracking, reset, preview re-render |
| `pipeline/__main__.py` (modify) | New flags/subcommands, dispatch-level locking, JSON wiring |
| `pipeline/driver.py` (modify) | `preview_photo`, `approve_review`, `process_all(stems, force)` |
| `pipeline/ingest.py` (modify) | `--from` staging ingest, `delivery_id`/`ingested_at` recording |
| `pipeline/recipe.py` (modify) | Atomic save; optional new-key support in `new()` |
| `pipeline/manifest.py` (modify) | Atomic save; non-persisting read path |
| `pipeline/render.py` (modify) | none beyond reuse — targeted preview logic lives in `driver.preview_photo` |
| `pipeline/subject.py` (modify) | `group_bbox_detail` (faces / no_faces / error outcome) |
| `tests/test_jsonio.py`, `tests/test_pp3.py`, `tests/test_provenance.py`, `tests/test_status.py`, `tests/test_adjust.py`, `tests/test_json_contract.py` (new) + additions to `tests/test_ingest.py`, `tests/test_driver.py`, `tests/test_cli.py` | Task-by-task coverage + golden fixtures |
| `tests/fixtures/json_contract/*.json` (new, committed) | Canonical contract artifacts consumed by Plan 2's XCTest |

---

### Task 1: `pipeline/jsonio.py` — JSON mode core

**Files:**
- Create: `pipeline/jsonio.py`
- Test: `tests/test_jsonio.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces (used by every later task):
  - `class CommandError(Exception)` with `.code: str`, `.message: str`, optional `.result: dict|None` — constructor `CommandError(code, message, result=None)`.
  - `activate() -> None`: saves the real stdout stream into module state, sets `sys.stdout = sys.stderr` (legacy prints → stderr). Idempotent.
  - `active() -> bool`.
  - `emit(event: dict) -> None`: one compact JSON line to the saved real stdout, flush; **no-op when not active**.
  - `finish_ok(result: dict) -> int`: writes `{"ok": true, "result": ...}` envelope line, returns 0.
  - `finish_error(code, message, result=None) -> int`: writes `{"ok": false, "error": {...}}` (plus `"result"` when given), returns 1.
  - `run_json(fn: Callable[[], dict]) -> int`: activates, calls `fn`, `finish_ok` on return; `CommandError` → `finish_error(e.code, e.message, e.result)`; `publish.LockError` → `LOCK_HELD`; any other `Exception` → `INTERNAL` with `str(e)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_jsonio.py
import io
import json
import sys

import pytest

from pipeline import jsonio, publish


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    # jsonio keeps module state; reset it per test.
    monkeypatch.setattr(jsonio, "_out", None)


def _capture(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(jsonio, "_real_stdout", lambda: buf)
    return buf


def test_emit_is_noop_when_inactive(monkeypatch):
    buf = _capture(monkeypatch)
    jsonio.emit({"event": "stage", "stem": "P1", "stage": "render"})
    assert buf.getvalue() == ""


def test_activate_redirects_legacy_prints_to_stderr(monkeypatch, capsys):
    _capture(monkeypatch)
    jsonio.activate()
    print("legacy chatter")
    captured = capsys.readouterr()
    assert "legacy chatter" in captured.err


def test_run_json_success_envelope_last_line_and_exit_zero(monkeypatch):
    buf = _capture(monkeypatch)

    def cmd():
        jsonio.emit({"event": "stage", "stem": "P1", "stage": "render"})
        return {"stem": "P1"}

    code = jsonio.run_json(cmd)
    lines = buf.getvalue().strip().splitlines()
    assert code == 0
    assert json.loads(lines[0]) == {"event": "stage", "stem": "P1",
                                    "stage": "render"}
    env = json.loads(lines[-1])
    assert env == {"ok": True, "result": {"stem": "P1"}}


def test_run_json_command_error_with_result(monkeypatch):
    buf = _capture(monkeypatch)

    def cmd():
        raise jsonio.CommandError("PARTIAL_FAILURE", "1 of 3 failed",
                                  result={"published": ["P1"]})

    code = jsonio.run_json(cmd)
    env = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert code == 1
    assert env["ok"] is False
    assert env["error"]["code"] == "PARTIAL_FAILURE"
    assert env["result"] == {"published": ["P1"]}


def test_run_json_maps_lock_error(monkeypatch):
    buf = _capture(monkeypatch)

    def cmd():
        raise publish.LockError("another driver instance holds lock")

    assert jsonio.run_json(cmd) == 1
    env = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert env["error"]["code"] == "LOCK_HELD"


def test_run_json_maps_unknown_exception_to_internal(monkeypatch):
    buf = _capture(monkeypatch)
    assert jsonio.run_json(lambda: 1 / 0) == 1
    env = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert env["error"]["code"] == "INTERNAL"
    assert "division" in env["error"]["message"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_jsonio.py -q`
Expected: FAIL — `ModuleNotFoundError: pipeline.jsonio` (or missing attributes).

- [ ] **Step 3: Implement `pipeline/jsonio.py`**

```python
import json
import sys

from . import publish

ERROR_CODES = frozenset({
    "LOCK_HELD", "TOOLCHAIN_FAILED", "RENDER_FAILED", "VERIFY_FAILED",
    "INVALID_STATE", "STALE_REVIEW", "PARTIAL_FAILURE", "NOT_FOUND",
    "BAD_INPUT", "INTERNAL",
})

# Saved NDJSON stream while JSON mode is active; None otherwise.
_out = None


class CommandError(Exception):
    def __init__(self, code, message, result=None):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.result = result


def _real_stdout():
    # Indirection point so tests can capture the NDJSON stream.
    return sys.__stdout__


def activate():
    global _out
    if _out is None:
        _out = _real_stdout()
        # Legacy print() calls throughout driver/ingest must not corrupt the
        # NDJSON stream; sending them to stderr changes no internal code.
        sys.stdout = sys.stderr


def active():
    return _out is not None


def _write(obj):
    _out.write(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")
    _out.flush()


def emit(event):
    if _out is not None:
        _write(event)


def finish_ok(result):
    _write({"ok": True, "result": result})
    return 0


def finish_error(code, message, result=None):
    envelope = {"ok": False, "error": {"code": code, "message": message}}
    if result is not None:
        envelope["result"] = result
    _write(envelope)
    return 1


def run_json(fn):
    activate()
    try:
        return finish_ok(fn())
    except CommandError as error:
        return finish_error(error.code, error.message, error.result)
    except publish.LockError as error:
        return finish_error("LOCK_HELD", str(error))
    except Exception as error:  # noqa: BLE001 — contract: never a bare traceback
        return finish_error("INTERNAL", f"{type(error).__name__}: {error}")
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_jsonio.py -q` — Expected: PASS.

- [ ] **Step 5: Full gate, then commit**

Run: `.venv/bin/python -m pytest tests/ -q` — Expected: all pass.

```bash
git add pipeline/jsonio.py tests/test_jsonio.py
git commit -m "feat(pipeline): jsonio core — envelopes, events, stdout discipline"
```

---

### Task 2: Atomic state writes + side-effect-free status read

**Files:**
- Modify: `pipeline/recipe.py:33-36` (`save`), `pipeline/manifest.py:15-27` (`load`/`save`), `pipeline/manifest.py:113-132` (`rebuild`)
- Test: `tests/test_manifest.py`, `tests/test_recipe.py` (additions)

**Interfaces:**
- Produces:
  - `recipe.save(stem, data)` — unchanged signature, now write-temp + `os.replace` in the same directory.
  - `manifest.save(m)` — same, atomic.
  - `manifest.rebuild(persist=True)` — existing behavior when `persist=True` (default); `persist=False` computes and returns the manifest **without writing**.
  - `manifest.load_readonly()` — like `load()` but uses `rebuild(persist=False)` in the recovery branch; never writes.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_manifest.py` and `tests/test_recipe.py`)

```python
# tests/test_manifest.py additions
def test_load_readonly_never_writes_manifest(tmp_repo):
    from pipeline import manifest, paths, recipe
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    assert not paths.manifest_path().exists()
    m = manifest.load_readonly()
    assert "P1" in m["photos"]
    assert not paths.manifest_path().exists()          # the point


def test_save_is_atomic_no_partial_file_on_same_name(tmp_repo):
    from pipeline import manifest, paths
    manifest.save({"photos": {}})
    # os.replace leaves no sibling temp files behind
    leftovers = [p for p in paths.root().iterdir()
                 if p.name.startswith(".manifest.") ]
    assert leftovers == []
```

```python
# tests/test_recipe.py additions
def test_recipe_save_atomic_leaves_no_temp(tmp_repo):
    from pipeline import paths, recipe
    recipe.save("P1", recipe.new("P1", "aa" * 32, 100, 80))
    assert (paths.recipes_dir() / "P1.yaml").exists()
    assert [p.name for p in paths.recipes_dir().iterdir()] == ["P1.yaml"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_manifest.py tests/test_recipe.py -q`
Expected: FAIL — `load_readonly` missing (the atomic tests may pass trivially before the change; that's fine, they pin the property).

- [ ] **Step 3: Implement**

In `pipeline/recipe.py` replace `save` body:

```python
import os, tempfile  # add to imports

def save(stem, data):
    p = _path(stem)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(yaml.safe_dump(data, sort_keys=True))
        os.replace(tmp, p)
    except BaseException:
        os.unlink(tmp)
        raise
```

In `pipeline/manifest.py`: same pattern for `save(m)` (temp in `paths.root()`, prefix `f".{p.name}."`, `os.replace`); change `rebuild()` signature to `rebuild(persist=True)` and guard the final `save(m)` with `if persist:`; add:

```python
def load_readonly():
    p = paths.manifest_path()
    if p.exists():
        return json.loads(p.read_text())
    if any(paths.recipes_dir().glob("*.yaml")):
        return rebuild(persist=False)
    return {"photos": {}}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_manifest.py tests/test_recipe.py -q` — PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/recipe.py pipeline/manifest.py tests/test_manifest.py tests/test_recipe.py
git commit -m "feat(pipeline): atomic recipe/manifest writes + read-only manifest path"
```

---

### Task 3: `pipeline/pp3.py` — line-preserving pp3 editor

**Files:**
- Create: `pipeline/pp3.py`
- Test: `tests/test_pp3.py`

**Interfaces:**
- Produces:
  - `class Pp3` — `Pp3.load(path: Path) -> Pp3` (missing file → empty document), `get(section, key) -> str|None`, `set(section, key, value)` (creates section at end if absent; replaces the key's line in place if present; appends to section otherwise), `remove(section, key) -> bool`, `section_keys(section) -> list[str]`, `dump() -> str`, `write_atomic(path)` (temp + `os.replace`).
  - Comments (`# …`), blank lines, unknown sections/keys, and line order are preserved byte-for-byte for untouched content. **Do not use `configparser`** — it drops comments and reorders keys; the hand-written sidecars must survive round-trips intact.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pp3.py
from pathlib import Path

from pipeline.pp3 import Pp3

REAL_SIDECAR = """# per-image override for P1036170 [vibrant] — layered over config/styles/vibrant.pp3
# Dusk frame: same warm-up as the natural sidecar so vibrance builds on
# honest skin tones instead of amplifying the cool cast.

[White Balance]
Setting=Custom
Temperature=5700
Green=1.0

[Exposure]
Compensation=0.12
CurveMode=Standard
Curve=1;0;0;0.25;0.22;0.75;0.78;1;1;
"""


def test_round_trip_preserves_bytes(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text(REAL_SIDECAR)
    doc = Pp3.load(p)
    assert doc.dump() == REAL_SIDECAR


def test_get_and_set_in_place(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text(REAL_SIDECAR)
    doc = Pp3.load(p)
    assert doc.get("White Balance", "Temperature") == "5700"
    doc.set("White Balance", "Temperature", "5450")
    out = doc.dump()
    assert "Temperature=5450" in out
    assert out.count("[White Balance]") == 1
    # Untouched keys and comments intact
    assert "Curve=1;0;0;0.25;0.22;0.75;0.78;1;1;" in out
    assert out.startswith("# per-image override")


def test_set_creates_missing_section_and_key(tmp_path):
    doc = Pp3.load(tmp_path / "missing.pp3")
    doc.set("White Balance", "Setting", "Custom")
    doc.set("White Balance", "Temperature", "5600")
    out = doc.dump()
    assert "[White Balance]\nSetting=Custom\nTemperature=5600" in out


def test_remove_and_section_keys(tmp_path):
    p = tmp_path / "s.pp3"
    p.write_text(REAL_SIDECAR)
    doc = Pp3.load(p)
    assert doc.remove("Exposure", "Compensation") is True
    assert doc.remove("Exposure", "Compensation") is False
    assert doc.get("Exposure", "Compensation") is None
    assert doc.section_keys("Exposure") == ["CurveMode", "Curve"]


def test_write_atomic(tmp_path):
    p = tmp_path / "s.pp3"
    doc = Pp3.load(p)
    doc.set("Exposure", "Compensation", "0.1")
    doc.write_atomic(p)
    assert p.read_text().rstrip().endswith("Compensation=0.1")
    assert [q.name for q in tmp_path.iterdir()] == ["s.pp3"]
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_pp3.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement `pipeline/pp3.py`**

```python
import os
import re
import tempfile
from pathlib import Path

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KEY_RE = re.compile(r"^(?P<key>[^=#;\s][^=]*)=(?P<value>.*)$")


class Pp3:
    """Line-preserving INI editor for RawTherapee .pp3 files.

    Untouched lines (comments, blanks, unknown keys) survive byte-for-byte;
    configparser would drop comments and reorder keys, destroying the
    hand-written sidecars adjust must preserve.
    """

    def __init__(self, lines):
        self._lines = lines

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls([])
        return cls(path.read_text().splitlines(keepends=True))

    def _section_span(self, section):
        start = None
        for i, line in enumerate(self._lines):
            m = _SECTION_RE.match(line)
            if m:
                if start is not None:
                    return start, i
                if m.group("name") == section:
                    start = i
        return (start, len(self._lines)) if start is not None else None

    def _find_key(self, section, key):
        span = self._section_span(section)
        if span is None:
            return None
        for i in range(span[0] + 1, span[1]):
            m = _KEY_RE.match(self._lines[i])
            if m and m.group("key").strip() == key:
                return i
        return None

    def get(self, section, key):
        i = self._find_key(section, key)
        if i is None:
            return None
        return _KEY_RE.match(self._lines[i]).group("value").strip()

    def set(self, section, key, value):
        line = f"{key}={value}\n"
        i = self._find_key(section, key)
        if i is not None:
            self._lines[i] = line
            return
        span = self._section_span(section)
        if span is None:
            if self._lines and not self._lines[-1].endswith("\n"):
                self._lines[-1] += "\n"
            if self._lines and self._lines[-1].strip():
                self._lines.append("\n")
            self._lines += [f"[{section}]\n", line]
            return
        end = span[1]
        while end > span[0] + 1 and not self._lines[end - 1].strip():
            end -= 1
        self._lines.insert(end, line)

    def remove(self, section, key):
        i = self._find_key(section, key)
        if i is None:
            return False
        del self._lines[i]
        return True

    def section_keys(self, section):
        span = self._section_span(section)
        if span is None:
            return []
        keys = []
        for i in range(span[0] + 1, span[1]):
            m = _KEY_RE.match(self._lines[i])
            if m:
                keys.append(m.group("key").strip())
        return keys

    def dump(self):
        return "".join(self._lines)

    def write_atomic(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(self.dump())
            os.replace(tmp, path)
        except BaseException:
            os.unlink(tmp)
            raise
```

Note on `_section_span`: it must return the span of the *requested* section, not the first section. The loop above is subtly wrong for a section that is not first — fix during implementation so the tests pass (track `start` only after matching the requested name; end at the next section header). The tests in Step 1 catch this (`Exposure` lookups in a two-section file).

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_pp3.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/pp3.py tests/test_pp3.py
git commit -m "feat(pipeline): line-preserving pp3 editor"
```

---

### Task 4: `pipeline/provenance.py` — input hashes, preview provenance, review_revision

**Files:**
- Create: `pipeline/provenance.py`
- Test: `tests/test_provenance.py`

**Interfaces:**
- Consumes: `recipe.load/fingerprint`, `render.style_hashes/seed_hash`, `toolchain.entries_for/RENDER_TOOLS`, `driver._lock`/`driver._lab` equivalents (re-implement locally to avoid importing driver: read `config/toolchain.lock` and `labprofile.load("generic-v1")`).
- Produces:
  - `style_input_hash(stem, style, rec) -> str` — sha256 of the canonical JSON of `{"raw": rec["raw_sha256"], "style": render.style_hashes(stem)[style], "seed": render.seed_hash(), "render_tools": toolchain.entries_for(lock, toolchain.RENDER_TOOLS), "overrides": rec["overrides"]}` (compact, sorted keys). This is exactly the material that determines preview pixels.
  - `content_hash(path) -> str|None` — sha256 of file bytes, `None` if missing; module-level cache keyed `(str(path), st_size, st_mtime_ns)` (cache key may use mtime; correctness comes from re-hashing when either changes).
  - `record_preview(rec, stem, style, preview_path) -> None` — sets `rec.setdefault("previews", {})[style] = {"inputs": style_input_hash(...), "content": content_hash(preview_path)}` (caller saves the recipe).
  - `stale_styles(stem, rec) -> list[str]` — styles where recorded `inputs` ≠ current `style_input_hash` OR recorded `content` ≠ current preview file hash OR no provenance recorded. Sorted.
  - `review_revision(stem, rec) -> str` — `"sha256:" + sha256(json({"fp": recipe.fingerprint(stem, rec, style_hashes, seed_hash, lock, lab), "previews": {style: content_hash(previews_dir()/f"{stem}_{style}_preview.jpg") for style in paths.STYLES}}))` — reuses the fingerprint's canonical blob so `status` and `approve` cannot drift.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provenance.py
import json

import pytest

from pipeline import paths, provenance, recipe


@pytest.fixture
def seeded(tmp_repo, monkeypatch):
    from pipeline import render, toolchain
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps(
        {"rawtherapee-cli": {"version": "5.12"}}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    rec = recipe.new("P1", "aa" * 32, 5776, 4336)
    recipe.save("P1", rec)
    return rec


def _fake_preview(tmp_repo, style, data=b"jpgbytes"):
    p = tmp_repo / "previews" / f"P1_{style}_preview.jpg"
    p.write_bytes(data)
    return p


def test_record_and_no_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    for style in paths.STYLES:
        p = _fake_preview(tmp_repo, style)
        provenance.record_preview(rec, "P1", style, p)
    recipe.save("P1", rec)
    assert provenance.stale_styles("P1", recipe.load("P1")) == []


def test_missing_provenance_is_stale(seeded):
    assert provenance.stale_styles("P1", recipe.load("P1")) == sorted(paths.STYLES)


def test_swapped_preview_content_is_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    p = _fake_preview(tmp_repo, "natural")
    provenance.record_preview(rec, "P1", "natural", p)
    for style in paths.STYLES:
        if style != "natural":
            provenance.record_preview(
                rec, "P1", style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    p.write_bytes(b"different pixels")            # swap the JPG, inputs unchanged
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_input_change_is_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    for style in paths.STYLES:
        provenance.record_preview(
            rec, "P1", style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    (tmp_repo / "sidecars" / "P1_natural.pp3").write_text(
        "[Exposure]\nCompensation=0.3\n")        # moves style_hashes → inputs
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_review_revision_moves_on_sidecar_and_preview_change(seeded, tmp_repo):
    rec = recipe.load("P1")
    r1 = provenance.review_revision("P1", rec)
    (tmp_repo / "sidecars" / "P1_bw.pp3").write_text("[Exposure]\nCompensation=0.2\n")
    r2 = provenance.review_revision("P1", recipe.load("P1"))
    assert r1 != r2
    _fake_preview(tmp_repo, "bw", b"new")
    r3 = provenance.review_revision("P1", recipe.load("P1"))
    assert r3 != r2
    assert r3.startswith("sha256:")
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_provenance.py -q` → FAIL.

- [ ] **Step 3: Implement `pipeline/provenance.py`**

```python
import hashlib
import json
from pathlib import Path

from . import labprofile, paths, recipe, render, toolchain

_LAB_PROFILE = "generic-v1"
_hash_cache = {}


def _lock():
    return json.loads((paths.config_dir() / "toolchain.lock").read_text())


def _canonical_sha(obj):
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def style_input_hash(stem, style, rec):
    return _canonical_sha({
        "raw": rec["raw_sha256"],
        "style": render.style_hashes(stem)[style],
        "seed": render.seed_hash(),
        "render_tools": toolchain.entries_for(_lock(), toolchain.RENDER_TOOLS),
        "overrides": rec["overrides"],
    })


def content_hash(path):
    path = Path(path)
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _hash_cache:
        _hash_cache[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _hash_cache[key]


def _preview_path(stem, style):
    return paths.previews_dir() / f"{stem}_{style}_preview.jpg"


def record_preview(rec, stem, style, preview_path):
    rec.setdefault("previews", {})[style] = {
        "inputs": style_input_hash(stem, style, rec),
        "content": content_hash(preview_path),
    }


def stale_styles(stem, rec):
    stored = rec.get("previews") or {}
    stale = []
    for style in paths.STYLES:
        entry = stored.get(style)
        if (entry is None
                or entry.get("inputs") != style_input_hash(stem, style, rec)
                or entry.get("content") != content_hash(_preview_path(stem, style))):
            stale.append(style)
    return sorted(stale)


def review_revision(stem, rec):
    fp = recipe.fingerprint(stem, rec, render.style_hashes(stem),
                            render.seed_hash(), _lock(),
                            labprofile.load(_LAB_PROFILE))
    previews = {style: content_hash(_preview_path(stem, style))
                for style in paths.STYLES}
    return "sha256:" + _canonical_sha({"fp": fp, "previews": previews})
```

Note: `fingerprint` requires `rec["previews"]`-free material only — it reads named keys, so the new optional `previews`/`app_adjustments`/`delivery_id` keys never enter the fingerprint. Do not add them to `recipe.fingerprint`.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_provenance.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/provenance.py tests/test_provenance.py
git commit -m "feat(pipeline): preview provenance + review_revision"
```

---

### Task 5: `driver.preview_photo` — atomic targeted preview with dims + provenance

**Files:**
- Modify: `pipeline/driver.py` (new function after `_record_render_dims`, ~line 86), `pipeline/driver.py:473-479` (`process_all` ingested branch), `pipeline/__main__.py:19-20` (`preview` subcommand)
- Test: `tests/test_driver.py` (additions)

**Interfaces:**
- Consumes: `render.rt_render`, `render.resolve_raw`, `provenance.record_preview`, `_dims`, `_record_render_dims`.
- Produces: `driver.preview_photo(stem, style) -> Path` —
  1. renders the preview JPG to `paths.run_dir()/f"preview-{stem}-{style}.tmp.jpg"` via `render.rt_render(raw, style, tmp, "jpg", 92)`;
  2. on success only: `os.replace(tmp, previews_dir()/f"{stem}_{style}_preview.jpg")` (failure leaves any existing preview untouched — rt_render raises before replace);
  3. reads dims via `_dims(final_path)` and calls `_record_render_dims(stem, rec, w, h)` **only if** `rec` has no recorded dims yet (preview JPGs and TIFs decode to identical dimensions per the GH7 5784×4344 behavior; a mismatch beyond the existing ±16 guard raises as today);
  4. `provenance.record_preview(rec, stem, style, final_path)`; `recipe.save(stem, rec)`.
- `process_all` ingested branch: replace `render.preview(stem, style)` with `preview_photo(stem, style)` (declared exception (b): batch previews now record provenance/dims keys).
- CLI `preview` keeps positional `stem style`; behavior now routes through `preview_photo` (exception (b)); still prints the output path. **Contract note:** the canonical CLI spelling for the targeted preview is the positional form `preview <stem> <style> [--json]`; the spec's `--stem/--style` phrasing maps to it and Plan 2's `PipelineClient` uses the positional form — do not add duplicate flag arguments.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_driver.py`)

```python
def test_preview_photo_atomic_and_records(tmp_repo, monkeypatch):
    import json as _json
    from pipeline import driver, paths, provenance, recipe, render, toolchain
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
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    monkeypatch.setattr(render, "resolve_raw", lambda stem: tmp_repo / "Input/P1.RW2")

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


def test_preview_photo_failure_keeps_previous_jpg(tmp_repo, monkeypatch):
    import json as _json
    from pipeline import driver, paths, recipe, render
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    monkeypatch.setattr(render, "resolve_raw", lambda stem: tmp_repo / "Input/P1.RW2")
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
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_driver.py -q -k preview_photo` → FAIL (`preview_photo` missing).

- [ ] **Step 3: Implement** — add to `pipeline/driver.py` (imports: `os`, `provenance` added to the package import list):

```python
def preview_photo(stem, style):
    if style not in paths.STYLES:
        raise ValueError(f"unknown style: {style}")
    rec = recipe.load(stem)
    raw = render.resolve_raw(stem)
    final = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
    tmp = paths.run_dir() / f"preview-{stem}-{style}.tmp.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.unlink(missing_ok=True)
    render.rt_render(raw, style, tmp, "jpg", 92)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, final)
    try:
        width, height = _render_dims(rec)
    except ValueError:
        width, height = _dims(final)
        _record_render_dims(stem, rec, width, height)
        rec = recipe.load(stem)  # _record_render_dims saved; reload before mutating
    provenance.record_preview(rec, stem, style, final)
    recipe.save(stem, rec)
    return final
```

In `process_all` (driver.py:475-476), replace `render.preview(stem, style)` with `preview_photo(stem, style)`. In `__main__.py:20`, replace the `preview` handler body with `print(driver.preview_photo(ns.stem, ns.style))` (import stays lazy via the existing `from . import driver`).

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_driver.py -q` → PASS. If any existing preview-path test asserts `render.preview` is called from `process_all`, update it here explicitly (declared exception (b)) and note the update in the commit message.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/driver.py pipeline/__main__.py tests/test_driver.py
git commit -m "feat(pipeline): atomic targeted preview with dims + provenance recording"
```

---

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
    from . import driver   # lazy: top-level import would be circular
    fingerprint = driver._current_fingerprint(stem)
    previews, hashes = {}, {}
    for style in paths.STYLES:
        p = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
        previews[style] = _rel(p) if p.exists() else None
        hashes[style] = provenance.content_hash(p)
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
        "review_revision": provenance.review_revision(stem, rec),
        "previews": previews,
        "preview_hashes": hashes,
        "stale_previews": provenance.stale_styles(stem, rec),
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


def _recipe_stamps():
    return {p: p.stat().st_mtime_ns
            for p in paths.recipes_dir().glob("*.yaml")}


def snapshot():
    for attempt in (0, 1):
        stamps = _recipe_stamps()
        m = manifest.load_readonly()
        problems = toolchain.verify(paths.config_dir() / "toolchain.lock")
        result = {
            "repo": str(paths.root()),
            "toolchain": {"ok": problems == [], "failures": problems},
            "lock": publish.lock_status(),
            "styles": list(paths.STYLES),
            "photos": [_photo(stem, m) for stem in sorted(m["photos"])],
        }
        if _recipe_stamps() == stamps or attempt == 1:
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
    assert "wb" not in recipe.load("P1")["app_adjustments"].get("vibrant", {})


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


def _write_control(rec, style, doc, control, values):
    section, keys = _CONTROLS[control]
    ownership = _own(rec, style)
    if control not in ownership:
        ownership[control] = {"previous": _capture_previous(doc, section, keys)}
    for key in keys:
        doc.set(section, key, values[key])
    ownership[control]["last_written"] = dict(values)


def _reset_control(rec, style, doc, control):
    section, keys = _CONTROLS[control]
    entry = _own(rec, style).get(control)
    if entry is None:
        return False
    current = _capture_previous(doc, section, keys)
    if current != entry.get("last_written"):
        del rec["app_adjustments"][style][control]     # diverged: hands off
        return False
    for key in keys:
        prior = entry["previous"].get(key)
        if prior is None:
            doc.remove(section, key)
        else:
            doc.set(section, key, prior)
    del rec["app_adjustments"][style][control]
    return True


def apply(stem, style, temperature=None, exposure=None, reset=False):
    _validate(style, temperature, exposure, reset)
    rec = _load_recipe(stem)
    revision_before = provenance.review_revision(stem, rec)
    side_path = paths.sidecars_dir() / f"{stem}_{style}.pp3"
    doc = pp3.Pp3.load(side_path)
    changed = False
    if reset:
        for control in _CONTROLS:
            changed |= _reset_control(rec, style, doc, control)
    else:
        if temperature is not None:
            _write_control(rec, style, doc, "wb", {
                "Setting": "Custom",
                "Temperature": str(int(temperature)),
                "Green": "1.0",
            })
            changed = True
        if exposure is not None:
            _write_control(rec, style, doc, "exposure",
                           {"Compensation": f"{float(exposure):g}"})
            changed = True
    if changed:
        doc.write_atomic(side_path)      # sidecar first…
        recipe.save(stem, rec)           # …recipe second (spec §4.2 crash rule)
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

### Task 8: Dispatch-level locking + `--json` on existing commands

**Files:**
- Modify: `pipeline/__main__.py` (all subcommands), `pipeline/subject.py` (add `group_bbox_detail`)
- Test: `tests/test_cli.py` (additions), `tests/test_subject.py` (addition)

**Interfaces:**
- Produces:
  - Every mutating subcommand (`ingest`, `preview`, `croppreview`, `approve`, `render`, `verify`) wrapped in `publish.acquire_lock()` at dispatch. **`run` is NOT wrapped** (process_all locks internally — Global Constraints). `status` and (Task 9's) `crops` never lock.
  - `--json` flag on `ingest`, `preview`, `approve`, `run` (results wired in their own tasks; this task wires `preview --json` → `{"stem", "style", "preview", "temperature", "exposure", "review_revision_before", "review_revision_after"}` via the same result builder as `adjust` (shared helper `adjust.preview_result(stem, style, revision_before)`) — factor the result dict out of `adjust.apply` into `adjust.preview_result` when implementing).
  - `subject.group_bbox_detail(image_path) -> tuple[dict|None, str]` returning `(bbox, "faces")`, `(None, "no_faces")`, or `(None, "detector_error")`; `group_bbox` becomes a thin wrapper returning only the bbox (existing callers unaffected).
- Legacy stdout guard: without `--json`, `ingest`/`preview`/`approve`/`run`/`status` print exactly what they print today.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py additions
import json
import subprocess
import sys


def _run(args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "pipeline", *args],
                          capture_output=True, text=True, env=env)


def test_mutating_command_reports_lock_held(tmp_repo, monkeypatch):
    import os
    (tmp_repo / "run").mkdir(exist_ok=True)
    (tmp_repo / "run/driver.lock").write_text(str(os.getpid()))  # live PID
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["ingest", "--json"], env=env)
    assert p.returncode == 1
    env_line = json.loads(p.stdout.strip().splitlines()[-1])
    assert env_line["error"]["code"] == "LOCK_HELD"


def test_status_never_locks(tmp_repo, monkeypatch):
    import os
    (tmp_repo / "run").mkdir(exist_ok=True)
    (tmp_repo / "run/driver.lock").write_text(str(os.getpid()))
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["status"], env=env)
    assert p.returncode == 0        # legacy status works while lock held


def test_legacy_status_output_unchanged(tmp_repo):
    import os
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["status"], env=env)
    assert p.returncode == 0
    assert p.stdout == "photos: none ingested\n"
```

```python
# tests/test_subject.py addition
def test_group_bbox_is_thin_wrapper_over_detail(monkeypatch):
    from pipeline import subject
    sentinel = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda path: (sentinel, "faces"))
    assert subject.group_bbox("whatever.jpg") is sentinel
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda path: (None, "detector_error"))
    assert subject.group_bbox("whatever.jpg") is None
```

(Additionally refactor the existing Vision tests in `tests/test_subject.py` — keep their skipif markers — to call `group_bbox_detail` and assert the basis string alongside the bbox: `"faces"` when a bbox is returned, `"no_faces"` for the zero-face image.)

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_cli.py -q` → FAIL (`--json` unknown argument).

- [ ] **Step 3: Implement**

Rewrite `pipeline/__main__.py` dispatch so each subcommand declares `mutating=True/False` and optional `--json`; a single helper runs the body:

```python
def _dispatch(ns, fn, mutating):
    from . import jsonio, publish

    def body():
        if mutating:
            with publish.acquire_lock():
                return fn(ns)
        return fn(ns)

    if getattr(ns, "json", False):
        return jsonio.run_json(lambda: body() or {})
    return _wrap(lambda _ns: body())(ns)
```

Mutating set: ingest, preview, croppreview, approve, render, verify, adjust. Non-mutating: status, crops. `run`: dispatched WITHOUT the lock wrapper (its `fn` calls `process_all`, which locks). Keep every legacy handler body identical so no-flag output is unchanged.

`pipeline/subject.py`: rename the body of `group_bbox` to `group_bbox_detail`, returning `(bbox, "faces")` on detection, `(None, "no_faces")` for zero faces, `(None, "detector_error")` in the existing exception paths; re-implement `group_bbox` as `return group_bbox_detail(image_path)[0]`.

- [ ] **Step 4: Run to verify pass** — `.venv/bin/python -m pytest tests/test_cli.py tests/test_subject.py -q` → PASS.

- [ ] **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/__main__.py pipeline/subject.py tests/test_cli.py tests/test_subject.py
git commit -m "feat(pipeline): dispatch-level locking + --json plumbing + group_bbox_detail"
```

---

### Task 9: `crops` command

**Files:**
- Modify: `pipeline/__main__.py` (new read-only subcommand), `pipeline/driver.py` (new `crop_windows` function near `approve`)
- Test: `tests/test_driver.py` (additions)

**Interfaces:**
- Consumes: `subject.group_bbox_detail`, `geometry.centered_crop_norm/subject_crop_norm`, `_render_dims`.
- Produces: `driver.crop_windows(stem) -> dict` — spec §4.3 `crops` result:
  - Persisted windows (recipe `crops` values non-None) → `source: "persisted"`, basis `"persisted"` → actually: result `basis` describes the *suggestion* path; when **all** windows are persisted, `basis: "persisted"`.
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
        return {"stem": stem, "basis": "persisted",
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

    rec = recipe.load(stem)                       # the single snapshot
    expected = review.get("expected_review_revision")
    if expected is not None:
        current = provenance.review_revision(stem, rec)
        if expected != current:
            raise jsonio.CommandError(
                "STALE_REVIEW",
                "review inputs changed since the reviewed snapshot")
        stale = provenance.stale_styles(stem, rec)
        if stale:
            raise jsonio.CommandError(
                "STALE_REVIEW", f"previews stale for styles: {stale}")

    try:
        width, height = _render_dims(rec)
    except ValueError as error:
        raise jsonio.CommandError("BAD_INPUT", str(error)) from error
    landscape = width >= height
    lab = _lab()
    for crop, window in windows.items():
        try:
            geometry.validate_crop(window, width, height, crop, landscape,
                                   lab["ppi"])
        except Exception as error:
            raise jsonio.CommandError(
                "BAD_INPUT", f"invalid {crop} window: {error}") from error

    rec["crops"] = {c: dict(windows[c]) for c in paths.CROPS}
    rec["expression_audit"] = list(audit)
    fingerprint = recipe.fingerprint(stem, rec, render.style_hashes(stem),
                                     render.seed_hash(), _lock(), lab)
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

Strip the `source` key from submitted windows if present before validation (`window = {k: v for k, v in window.items() if k in ("x", "y", "w", "h")}`) — the app echoes `crops`-command windows back. `__main__.py`: `approve` gains `--review-file` (path) and `--json`; with `--review-file`, handler reads the JSON file and calls `approve_review`; without it, legacy `driver.approve(ns.stem)` untouched.

- [ ] **Step 4: Run to verify pass**, **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/driver.py pipeline/__main__.py tests/test_driver.py
git commit -m "feat(pipeline): approve --review-file with STALE_REVIEW gates"
```

---

### Task 11: `ingest --from` / `--delivery-id`

**Files:**
- Modify: `pipeline/ingest.py` (`run` signature, new `stage_sources`), `pipeline/recipe.py:14-26` (`new` gains optional metadata), `pipeline/__main__.py` (`ingest` flags + JSON result)
- Test: `tests/test_ingest.py` (additions)

**Interfaces:**
- Produces:
  - `recipe.new(stem, raw_sha256, width, height, delivery_id=None, ingested_at=None)` — the two new keys are set **only when not None** (flag-less ingest produces byte-identical legacy recipes).
  - `ingest.stage_sources(sources: list[Path]) -> dict` — for each source file (recursing one level into dropped directories, case-insensitive `.rw2` filter): copy to `Input/.staging-<uuid4hex>/<name>`, hash the **temp** (never the live source), then decide: hash in `_archived_hashes()` or an already-staged/`Input/` file with same hash → `skipped` (`"duplicate content"`); same stem exists in `Input/` or manifest with different hash → `conflicts` (`"stem exists with different content"`), staged copy deleted; otherwise `os.replace` temp into `Input/`. Unreadable source → `failed` entry `{"file", "code": "BAD_INPUT", "message"}`. Returns `{"placed": [names], "skipped": [...], "conflicts": [...], "failed": [...]}`; always removes the staging dir.
  - `ingest.run(delivery_id=None)` — existing behavior; when `delivery_id` is not None, passes `delivery_id` and `ingested_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")` into `recipe.new`.
  - JSON result for the command (built in `__main__.py` from `stage_sources` + `run` outputs): `{"ingested": [...], "skipped": [...], "conflicts": [...], "failed": [...]}`; non-empty `failed` → `CommandError("PARTIAL_FAILURE", f"{len(failed)} file(s) failed", result=result)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_ingest.py`)

```python
def test_recipe_new_without_flags_is_legacy_bytes(tmp_repo):
    from pipeline import recipe
    legacy = recipe.new("P1", "aa" * 32, 100, 80)
    assert "delivery_id" not in legacy and "ingested_at" not in legacy
    tagged = recipe.new("P1", "aa" * 32, 100, 80,
                        delivery_id="u-1", ingested_at="2026-08-12T00:00:00Z")
    assert tagged["delivery_id"] == "u-1"


def test_stage_sources_hashes_temp_and_places(tmp_repo):
    from pipeline import ingest, paths
    src = tmp_repo / "elsewhere"; src.mkdir()
    f = src / "P9.RW2"; f.write_bytes(b"raw-bytes")
    result = ingest.stage_sources([f])
    assert result["placed"] == ["P9.RW2"]
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"raw-bytes"
    assert not any(p.name.startswith(".staging-")
                   for p in paths.input_dir().iterdir())


def test_stage_sources_conflict_and_duplicate(tmp_repo):
    from pipeline import ingest, paths
    (paths.input_dir() / "P9.RW2").write_bytes(b"original")
    src = tmp_repo / "elsewhere"; src.mkdir()
    dup = src / "P8.RW2"; dup.write_bytes(b"original")      # same content, new stem → placed
    clash = src / "P9.RW2"; clash.write_bytes(b"DIFFERENT") # same stem, new content → conflict
    result = ingest.stage_sources([dup, clash])
    assert result["placed"] == ["P8.RW2"]
    assert result["conflicts"][0]["file"] == "P9.RW2"
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"original"


def test_run_records_delivery_metadata_only_when_given(tmp_repo, monkeypatch):
    from pipeline import ingest, recipe
    monkeypatch.setattr(ingest, "exif_summary", lambda p: {
        "Make": "Panasonic", "Model": "DC-GH7", "ImageWidth": 5776,
        "ImageHeight": 4336, "Orientation": "Horizontal (normal)",
        "LensModel": "L", "ISO": 200, "ExposureTime": "1/100",
        "AspectRatio": "4:3"})
    (tmp_repo / "Input/P7.rw2").write_bytes(b"bytes-7")
    ingest.run(delivery_id="uuid-7")
    rec = recipe.load("P7")
    assert rec["delivery_id"] == "uuid-7"
    assert rec["ingested_at"].endswith("Z")
```

- [ ] **Step 2: Run to verify failure** — `.venv/bin/python -m pytest tests/test_ingest.py -q` → FAIL.

- [ ] **Step 3: Implement**

`recipe.new`: add keyword-only params; after building the dict, `if delivery_id is not None: data["delivery_id"] = delivery_id` and same for `ingested_at`.

`ingest.stage_sources`:

```python
import uuid
import os


def _iter_sources(sources):
    for source in map(Path, sources):
        if source.is_dir():
            yield from (p for p in sorted(source.iterdir())
                        if p.is_file() and p.suffix.lower() == ".rw2")
        elif source.suffix.lower() == ".rw2":
            yield source


def stage_sources(sources):
    result = {"placed": [], "skipped": [], "conflicts": [], "failed": []}
    staging = paths.input_dir() / f".staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True)
    known_hashes = _archived_hashes()
    known_hashes |= {_sha256(p) for p in paths.input_dir().iterdir()
                     if p.is_file() and p.suffix.lower() == ".rw2"}
    manifest_stems = set(manifest.load()["photos"])
    input_stems = {p.stem for p in paths.input_dir().iterdir()
                   if p.is_file() and p.suffix.lower() == ".rw2"}
    try:
        for source in _iter_sources(sources):
            try:
                temp = staging / source.name
                shutil.copy2(source, temp)
                digest = _sha256(temp)           # hash the staged copy
            except OSError as error:
                result["failed"].append({"file": source.name,
                                         "code": "BAD_INPUT",
                                         "message": str(error)})
                continue
            if digest in known_hashes:
                temp.unlink()
                result["skipped"].append({"file": source.name,
                                          "reason": "duplicate content"})
                continue
            if source.stem in manifest_stems | input_stems:
                temp.unlink()
                result["conflicts"].append(
                    {"file": source.name,
                     "reason": "stem exists with different content"})
                continue
            os.replace(temp, paths.input_dir() / source.name)
            known_hashes.add(digest)
            input_stems.add(source.stem)
            result["placed"].append(source.name)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return result
```

`ingest.run(delivery_id=None)`: thread the two values into `recipe.save(stem, recipe.new(..., delivery_id=delivery_id, ingested_at=_now_utc() if delivery_id else None))` with `_now_utc()` as specified in Interfaces. `__main__.py`: `ingest` gains `--from` (`nargs="+"`), `--delivery-id`, `--json`; JSON handler composes `stage_sources` (when `--from`) + `run(delivery_id)` results into the contract shape, mapping `run()`'s `"ok"` entries to `ingested` and its `"failed: …"` strings into `failed` entries (`code: "BAD_INPUT"`); raises `PARTIAL_FAILURE` with attached result when `failed` non-empty. Legacy no-flag path calls `_ingest()` unchanged.

- [ ] **Step 4: Run to verify pass**, **Step 5: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add pipeline/ingest.py pipeline/recipe.py pipeline/__main__.py tests/test_ingest.py
git commit -m "feat(pipeline): ingest --from staged-copy ingest + delivery metadata"
```

---

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
    import io, json as _json
    from pipeline import jsonio
    events = []
    monkeypatch.setattr(jsonio, "_out", io.StringIO())
    monkeypatch.setattr(jsonio, "emit",
                        lambda e: events.append(e))
    # render_photo internals are exercised via the existing
    # test_render_photo_records_dims_and_strips_before_pdfs fixture pattern;
    # reuse its monkeypatching and assert at least one progress event with
    # stage == "render" and 1-based index arrived in `events`.
```

(Complete the last test by copying the monkeypatch scaffolding from the existing `test_render_photo_records_dims_and_strips_before_pdfs` in this file — fake `render.rt_render`, `crops.jpg_from_tif`, `pdfs.wrap`, `pdfs.comparison_sheet`, `metadata.strip`, `_dims` — then assert on `events`.)

- [ ] **Step 2: Run to verify failure** — `-k "stem_scoping or force_rerenders or collect_shapes"` → FAIL (unexpected kwargs).

- [ ] **Step 3: Implement** — mechanical per the Interfaces block: add the three keyword params with legacy-identical defaults; add the loop filter; add the force reset; thread `collect` appends and `jsonio.emit` calls at the named points. `_finish_verified(data, stem, collect=None)` gains the optional param. `__main__.py` `run`: `--stem`, `--force`, `--json`; JSON path builds `collect={}`, calls `process_all(stems={ns.stem} if ns.stem else None, force=ns.force, collect=collect)`, raises `PARTIAL_FAILURE` when `collect["failed"]`; legacy path calls `process_all()` bare.

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

### Task 13: Golden contract fixtures + no-flag regression sweep

**Files:**
- Create: `tests/test_json_contract.py`, `tests/fixtures/json_contract/` (committed outputs)
- Test: itself

**Interfaces:**
- Consumes: everything above, via `pipeline.__main__.main([...])` in-process with `jsonio._real_stdout` monkeypatched to a buffer.
- Produces: committed fixtures `status_empty.json`, `status_ingested.json`, `adjust_ok.json`, `crops_suggested.json`, `approve_stale_review.json`, `ingest_result.json`, `run_partial_failure.json`, `envelope_lock_held.json` — each the **normalized** final envelope (plus, for `adjust_ok`, the full NDJSON line list). Plan 2's XCTest decodes these files verbatim.
- Normalization (deterministic fixtures): replace the tmp repo path with `<REPO>`, every 64-hex sha with `<SHA256>`, every `sha256:…` revision with `<REVISION>`, RFC 3339 timestamps with `<TIMESTAMP>`. The normalizer lives in the test module and is applied before compare/write.
- Regen mode: `REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py` rewrites the fixtures; default mode compares and fails on drift.

- [ ] **Step 1: Write the test module** — scenario builders reuse the seeding helpers from `tests/test_status.py`/`tests/test_adjust.py` patterns (minimal styles, lock file, lab profile, monkeypatched `toolchain.verify`/`entries_for`, fake `driver.preview_photo`). Each scenario: run `main([cmd, ..., "--json"])`, capture the buffer, normalize, then `assert normalized == fixture_path.read_text()` (or write when regen env var set, then still assert). Include one scenario asserting **byte-identical legacy output**: `main(["status"])` with stdout captured equals `"photos: none ingested\n"`, and `main(["ingest"])` output equals today's format for an empty `Input/`.

- [ ] **Step 2: Generate fixtures** — `REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py -q` then inspect each file by eye against spec §4.3.

- [ ] **Step 3: Run in compare mode** — `.venv/bin/python -m pytest tests/test_json_contract.py -q` → PASS.

- [ ] **Step 4: Full gate + commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add tests/test_json_contract.py tests/fixtures/json_contract/
git commit -m "test(pipeline): golden JSON contract fixtures + legacy output guards"
```

---

## Self-Review (run after writing, before offering execution)

1. **Spec coverage:** §4.2 command table → Tasks 5–12; §4.3 contract → Tasks 1, 6, 13; atomic writes/status purity → Task 2; pp3/ownership → Tasks 3, 7; provenance/revision → Task 4; `group_bbox_detail` → Task 8; locking model → Tasks 7, 8 + Global Constraints. Spec §5–§7 (UI) and §8's Swift/XCTest halves are **Plan 2**.
2. **Placeholder scan:** none — every step carries runnable code or an exact mechanical instruction anchored to code shown in an earlier task.
3. **Type consistency:** `CommandError(code, message, result=None)` used in Tasks 7, 9, 10, 11, 12; `preview_photo(stem, style) -> Path` consumed in Tasks 7 (monkeypatched) and 5; `review_revision(stem, rec)` consumed in Tasks 6, 7, 10; `stage_sources` result keys match Task 11's CLI composition; `process_all(stems, force, collect)` matches Task 12's CLI call.
