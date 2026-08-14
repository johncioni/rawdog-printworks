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

# The interpreter's stdout as it was before activate() redirected it.
_saved_stdout = None


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
    global _out, _saved_stdout
    if _out is None:
        _out = _real_stdout()
        # Legacy print() calls throughout driver/ingest must not corrupt the
        # NDJSON stream; sending them to stderr changes no internal code.
        _saved_stdout = sys.stdout
        sys.stdout = sys.stderr


def deactivate():
    """Undo activate(). The redirect is process-global, so the module owns
    putting it back rather than leaving callers (and tests) to compensate."""
    global _out, _saved_stdout
    if _out is not None:
        sys.stdout = _saved_stdout
        _out = None
        _saved_stdout = None


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
    finally:
        # The envelope is already written; restore the interpreter's stdout so
        # JSON mode leaves no process-global state behind.
        deactivate()
