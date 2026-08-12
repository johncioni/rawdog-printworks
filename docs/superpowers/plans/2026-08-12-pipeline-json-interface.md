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
  - `run_json(fn: Callable[[], dict], adapters: dict[type, str] | None = None) -> int`: activates, calls `fn`, `finish_ok` on return; `CommandError` → `finish_error(e.code, e.message, e.result)`; `publish.LockError` → `LOCK_HELD`; an exception matching an `adapters` entry (isinstance, first match in insertion order) → that code with `str(e)`; any other `Exception` → `INTERNAL` with `f"{type(e).__name__}: {e}"`. Task 8's dispatch passes the standard adapter set per command: `{render.RenderError: "RENDER_FAILED", ingest.IngestError: "BAD_INPUT", FileNotFoundError: "NOT_FOUND"}`, and commands that surface toolchain drift (`run`) additionally map the `"toolchain drift"` `RuntimeError` from `process_all` to `TOOLCHAIN_FAILED` by raising `CommandError` at the command boundary (a message-match adapter is too fragile; catch and re-raise typed).

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


def test_run_json_adapters_map_typed_exceptions(monkeypatch):
    buf = _capture(monkeypatch)

    class Boom(Exception):
        pass

    assert jsonio.run_json(lambda: (_ for _ in ()).throw(Boom("rt died")),
                           adapters={Boom: "RENDER_FAILED"}) == 1
    env = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert env["error"] == {"code": "RENDER_FAILED", "message": "rt died"}
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


def run_json(fn, adapters=None):
    activate()
    try:
        return finish_ok(fn())
    except CommandError as error:
        return finish_error(error.code, error.message, error.result)
    except publish.LockError as error:
        return finish_error("LOCK_HELD", str(error))
    except Exception as error:  # noqa: BLE001 — contract: never a bare traceback
        for exc_type, code in (adapters or {}).items():
            if isinstance(error, exc_type):
                return finish_error(code, str(error))
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
  - `style_input_hash(stem, style, rec, material=None) -> str` — sha256 of the canonical JSON of `{"raw": rec["raw_sha256"], "style": material["style_hashes"][style], "seed": material["seed_hash"], "render_tools": toolchain.entries_for(material["lock"], toolchain.RENDER_TOOLS), "overrides": rec["overrides"]}` (compact, sorted keys; `material=None` → `gather_material(stem)`). This is exactly the material that determines preview pixels — which requires (Task 5) that targeted previews actually render with the denoise extra profile when `overrides["denoise"]` is set, and verify the RAW hash, or the hash certifies inputs that weren't used.
  - `content_hash(path) -> str|None` — sha256 of file bytes, `None` if missing. **No caching**: a mtime/size cache would let a same-size, restored-mtime replacement return a stale hash, defeating the spec's same-mtime guarantee (§4.2). Preview hashing is ~24 MB per status call (~25 ms) — cheap at human refresh rates.
  - `gather_material(stem) -> dict` — reads `render.style_hashes(stem)`, `render.seed_hash()`, the toolchain lock, and the lab profile **once** and returns them as `{"style_hashes", "seed_hash", "lock", "lab"}`; every function below accepts an optional `material=` so `approve_review` and `status` derive revision, staleness, and fingerprint from one read (the single-snapshot rule).
  - `record_preview(rec, stem, style, preview_path, inputs_hash) -> None` — sets `rec.setdefault("previews", {})[style] = {"inputs": inputs_hash, "content": content_hash(preview_path)}` (caller saves the recipe). **`inputs_hash` is computed by the caller BEFORE rendering starts** (Task 5) — recording a post-render hash would certify inputs edited during the render.
  - `stale_styles(stem, rec, material=None) -> list[str]` — styles where recorded `inputs` ≠ current `style_input_hash` OR recorded `content` ≠ current preview file hash OR no provenance recorded. Sorted.
  - `review_revision(stem, rec, material=None) -> str` — `"sha256:" + sha256(json({"fp": recipe.fingerprint(stem, rec, material["style_hashes"], material["seed_hash"], material["lock"], material["lab"]), "previews": {style: content_hash(previews_dir()/f"{stem}_{style}_preview.jpg") for style in paths.STYLES}}))` — reuses the fingerprint's canonical blob so `status` and `approve` cannot drift.

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


def _record(rec, style, p):
    provenance.record_preview(
        rec, "P1", style, p, provenance.style_input_hash("P1", style, rec))


def test_record_and_no_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    for style in paths.STYLES:
        _record(rec, style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    assert provenance.stale_styles("P1", recipe.load("P1")) == []


def test_same_size_restored_mtime_swap_is_stale(seeded, tmp_repo):
    import os
    rec = recipe.load("P1")
    p = _fake_preview(tmp_repo, "natural", b"AAAAAAAA")
    for style in paths.STYLES:
        _record(rec, style, _fake_preview(tmp_repo, style)
                if style != "natural" else p)
    recipe.save("P1", rec)
    st = p.stat()
    p.write_bytes(b"BBBBBBBB")                       # same size
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # restored mtime
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_missing_provenance_is_stale(seeded):
    assert provenance.stale_styles("P1", recipe.load("P1")) == sorted(paths.STYLES)


def test_swapped_preview_content_is_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    p = _fake_preview(tmp_repo, "natural")
    _record(rec, "natural", p)
    for style in paths.STYLES:
        if style != "natural":
            _record(rec, style, _fake_preview(tmp_repo, style))
    recipe.save("P1", rec)
    p.write_bytes(b"different pixels")            # swap the JPG, inputs unchanged
    assert "natural" in provenance.stale_styles("P1", recipe.load("P1"))


def test_input_change_is_stale(seeded, tmp_repo):
    rec = recipe.load("P1")
    for style in paths.STYLES:
        _record(rec, style, _fake_preview(tmp_repo, style))
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


def gather_material(stem):
    return {
        "style_hashes": render.style_hashes(stem),
        "seed_hash": render.seed_hash(),
        "lock": json.loads((paths.config_dir() / "toolchain.lock").read_text()),
        "lab": labprofile.load(_LAB_PROFILE),
    }


def _canonical_sha(obj):
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def style_input_hash(stem, style, rec, material=None):
    material = material or gather_material(stem)
    return _canonical_sha({
        "raw": rec["raw_sha256"],
        "style": material["style_hashes"][style],
        "seed": material["seed_hash"],
        "render_tools": toolchain.entries_for(material["lock"],
                                              toolchain.RENDER_TOOLS),
        "overrides": rec["overrides"],
    })


def content_hash(path):
    # Deliberately uncached: a size+mtime cache would let a same-size,
    # restored-mtime swap return a stale hash (spec §4.2 forbids exactly that).
    path = Path(path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _preview_path(stem, style):
    return paths.previews_dir() / f"{stem}_{style}_preview.jpg"


def record_preview(rec, stem, style, preview_path, inputs_hash):
    rec.setdefault("previews", {})[style] = {
        "inputs": inputs_hash,
        "content": content_hash(preview_path),
    }


def stale_styles(stem, rec, material=None):
    material = material or gather_material(stem)
    stored = rec.get("previews") or {}
    stale = []
    for style in paths.STYLES:
        entry = stored.get(style)
        if (entry is None
                or entry.get("inputs") != style_input_hash(stem, style, rec,
                                                           material)
                or entry.get("content") != content_hash(_preview_path(stem, style))):
            stale.append(style)
    return sorted(stale)


def review_revision(stem, rec, material=None):
    material = material or gather_material(stem)
    fp = recipe.fingerprint(stem, rec, material["style_hashes"],
                            material["seed_hash"], material["lock"],
                            material["lab"])
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
- Produces: `driver.preview_photo(stem, style) -> Path`, in this exact order (each step's failure leaves the previous preview AND recipe untouched):
  1. load `rec`; **verify the RAW**: `_sha256(render.resolve_raw(stem)) == rec["raw_sha256"]` else `RuntimeError` (same message pattern as `render_photo`, driver.py:207-211);
  2. **capture the pre-render input snapshot**: `material = provenance.gather_material(stem)`; `inputs_hash = provenance.style_input_hash(stem, style, rec, material)` — computed BEFORE rendering so an edit landing mid-render produces a mismatch on the next staleness check instead of being certified;
  3. render to `paths.run_dir()/f"preview-{stem}-{style}.tmp.jpg"` via `render.rt_render(raw, style, tmp, "jpg", 92, extra_profiles=(render.denoise_profile(),) if rec["overrides"].get("denoise") else ())` — same denoise handling as `render_photo`, or the inputs hash (which covers `overrides`) would describe profiles that weren't applied;
  4. **validate the temp before touching anything**: `_dims(tmp)` (±16 guard via `_record_render_dims` semantics), then compose ONE recipe update in memory: render dims (if not yet recorded) + `provenance.record_preview(rec, stem, style, tmp, inputs_hash)`;
  5. `os.replace(tmp, final)` then one `recipe.save(stem, rec)` — the recipe's recorded content hash is of the temp bytes, which are byte-identical to `final` after the rename.
- `process_all` ingested branch: replace `render.preview(stem, style)` with `preview_photo(stem, style)` (declared exception (b): batch previews now record provenance/dims keys).
- CLI `preview` keeps positional `stem style` (legacy, unchanged spelling) AND accepts the spec's flagged form: parser uses `p.add_argument("stem", nargs="?")`, `p.add_argument("style", nargs="?")`, `p.add_argument("--stem", dest="stem_flag")`, `p.add_argument("--style", dest="style_flag")`; handler resolves `stem = ns.stem_flag or ns.stem` (error `BAD_INPUT` if neither or both). **The flagged form is the JSON-mode canonical spelling** (`preview --stem S --style Y --json`) and is what Plan 2's `PipelineClient` sends; the positional form remains for humans and legacy scripts. Both route through `preview_photo`; still prints the output path in non-JSON mode.

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

    # Validate + compose the full recipe update BEFORE the swap: a failure
    # here must leave both the old preview and the recipe untouched.
    try:
        width, height = _render_dims(rec)
    except ValueError:
        width, height = _dims(tmp)
        if (abs(width - int(rec["width"])) > 16
                or abs(height - int(rec["height"])) > 16):
            raise RuntimeError(
                f"render dimensions {width}x{height} differ from declared "
                f"{rec['width']}x{rec['height']} by more than 16 pixels")
        rec["render_width"], rec["render_height"] = width, height
    provenance.record_preview(rec, stem, style, tmp, inputs_hash)

    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, final)
    recipe.save(stem, rec)
    return final
```

(Recorded content hash is of the temp bytes — byte-identical to `final` after `os.replace`. Add a test: `overrides["denoise"] = True` → the fake `rt_render` receives one extra profile; and a test that a `_dims` failure on the temp leaves the previous preview file and recipe bytes unchanged.)

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
    # One recipe load + one material gather per photo; the fingerprint is
    # computed from THIS rec, never a re-read (coherence with review_revision).
    material = provenance.gather_material(stem)
    fingerprint = recipe.fingerprint(
        stem, rec, material["style_hashes"], material["seed_hash"],
        material["lock"], material["lab"])
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
    from . import ingest, jsonio, publish, render

    def body():
        if mutating:
            with publish.acquire_lock():
                return fn(ns)
        return fn(ns)

    if getattr(ns, "json", False):
        return jsonio.run_json(
            lambda: body() or {},
            adapters={render.RenderError: "RENDER_FAILED",
                      ingest.IngestError: "BAD_INPUT",
                      FileNotFoundError: "NOT_FOUND"})
    return _wrap(lambda _ns: body())(ns)
```

The `run --json` handler (Task 12) additionally catches the toolchain-drift `RuntimeError` raised by `process_all` (message starts `"toolchain drift"`) and re-raises `jsonio.CommandError("TOOLCHAIN_FAILED", str(e))`; verify failures inside a collected run surface per-stem as `VERIFY_FAILED` entries in `result.failed`, not as exceptions.

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
    # Same CONTENT under a new stem is still a content duplicate → skipped
    # (spec §4.2/§5.4: content-hash dedup), never placed.
    dup = src / "P8.RW2"; dup.write_bytes(b"original")
    clash = src / "P9.RW2"; clash.write_bytes(b"DIFFERENT") # same stem, new content → conflict
    result = ingest.stage_sources([dup, clash])
    assert result["placed"] == []
    assert result["skipped"][0]["file"] == "P8.RW2"
    assert result["conflicts"][0]["file"] == "P9.RW2"
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"original"
    assert not (paths.input_dir() / "P8.RW2").exists()


def test_stage_sources_hashes_the_staged_temp_not_the_live_source(
        tmp_repo, monkeypatch):
    import shutil as real_shutil
    from pipeline import ingest, paths
    src = tmp_repo / "elsewhere"; src.mkdir()
    f = src / "P9.RW2"; f.write_bytes(b"first-bytes")

    def mutating_copy(source, dest):
        real_shutil.copy2(source, dest)
        Path(source).write_bytes(b"MUTATED-AFTER-COPY")   # source changes mid-flight
    monkeypatch.setattr(ingest.shutil, "copy2", mutating_copy)

    result = ingest.stage_sources([f])
    # Decision and placement reflect the STAGED bytes; the mutated live
    # source never influences the outcome or lands in Input/.
    assert result["placed"] == ["P9.RW2"]
    assert (paths.input_dir() / "P9.RW2").read_bytes() == b"first-bytes"


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

### Task 13: Golden contract fixtures + no-flag regression sweep

**Files:**
- Create: `tests/test_json_contract.py`, `tests/fixtures/json_contract/` (committed outputs)
- Test: itself

**Interfaces:**
- Consumes: everything above, via `pipeline.__main__.main([...])` in-process with `jsonio._real_stdout` monkeypatched to a buffer.
- Produces: committed fixtures — each file is the **normalized final envelope only** (one JSON object): `status_empty.json`, `status_ingested.json`, `adjust_ok.json`, `crops_suggested.json`, `approve_stale_review.json`, `ingest_result.json`, `run_partial_failure.json`, `envelope_lock_held.json`; plus `adjust_stream.ndjson` — the full normalized NDJSON line list (events + envelope) from the adjust scenario, for Plan 2's streaming-parser tests. Plan 2's XCTest decodes the `.json` files as envelopes and the `.ndjson` file line-by-line.
- JSON-mode state hygiene: `jsonio` keeps module state (`_out`, redirected `sys.stdout`); the test module uses an autouse fixture that saves/restores `sys.stdout` and resets `jsonio._out = None` around every scenario, or back-to-back in-process `main()` calls bleed into each other.
- Scenario definitions (exact; each seeds a fresh `tmp_repo` with the styles/lock/lab-profile pattern from `tests/test_status.py`, monkeypatched `toolchain.verify → []`, `toolchain.entries_for → {}`, and a fake `driver.preview_photo` writing deterministic bytes):
  1. `status_empty` — no photos; `main(["status", "--json"])`.
  2. `status_ingested` — one recipe (fixed bytes `b"raw-bytes"`, delivery fields set), manifest state `ingested`, previews recorded via the fake; `main(["status", "--json"])`.
  3. `adjust_ok` + `adjust_stream` — same repo; `main(["adjust", "--stem", "P1", "--style", "natural", "--temperature", "5600", "--json"])`; envelope → `adjust_ok.json`, full captured line list → `adjust_stream.ndjson`.
  4. `crops_suggested` — recipe with recorded dims, no persisted crops, `subject.group_bbox_detail` monkeypatched to a fixed bbox; `main(["crops", "--stem", "P1", "--json"])`.
  5. `approve_stale_review` — review-file with `expected_review_revision: "sha256:wrong"`; `main(["approve", "--stem", "P1", "--review-file", path, "--json"])`.
  6. `ingest_result` — one placeable source + one stem conflict via `--from`; `main(["ingest", "--from", src1, src2, "--delivery-id", "fixture-uuid", "--json"])`.
  7. `run_partial_failure` — two approved stems, `verify_photo` monkeypatched to fail for one; `main(["run", "--json"])`.
  8. `envelope_lock_held` — lock file held by a live PID (`os.getpid()`); `main(["ingest", "--json"])`.
- Normalization (deterministic fixtures): replace the tmp repo path with `<REPO>`, every 64-hex sha with `<SHA256>`, every `sha256:…` revision with `<REVISION>`, RFC 3339 timestamps with `<TIMESTAMP>`. The normalizer lives in the test module and is applied before compare/write.
- Regen mode: `REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py` rewrites the fixtures; default mode compares and fails on drift.

- [ ] **Step 1: Write the test module** — one test per scenario from the Interfaces list, each: seed per the scenario definition → run `main([...])` in-process with `jsonio._real_stdout` monkeypatched to a buffer → normalize → `assert normalized == fixture_path.read_text()` (or write when `REGEN_CONTRACT_FIXTURES=1`, then still assert). The autouse stdout/`jsonio._out` reset fixture from Interfaces wraps every test. Include two legacy-output guards: `main(["status"])` stdout equals `"photos: none ingested\n"` exactly, and `main(["ingest"])` on an empty `Input/` equals today's output exactly (capture today's format before implementing by running the command).

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
