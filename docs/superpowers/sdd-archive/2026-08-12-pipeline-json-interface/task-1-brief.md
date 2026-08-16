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

