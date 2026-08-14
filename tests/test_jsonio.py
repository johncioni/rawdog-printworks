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
    before = sys.stdout
    jsonio.activate()
    print("legacy chatter")
    captured = capsys.readouterr()
    assert "legacy chatter" in captured.err

    # Containment is the module's job, not the fixture teardown's.
    jsonio.deactivate()
    assert sys.stdout is before
    assert not jsonio.active()


def test_run_json_restores_stdout_even_when_the_command_raises(monkeypatch):
    _capture(monkeypatch)
    before = sys.stdout

    def cmd():
        raise RuntimeError("boom")

    assert jsonio.run_json(cmd) == 1
    assert sys.stdout is before
    assert not jsonio.active()


def test_command_error_rejects_a_code_outside_the_contract():
    # The guard is what keeps the error-code set closed; a typo at a call site
    # would otherwise surface as an INTERNAL envelope.
    with pytest.raises(ValueError):
        jsonio.CommandError("NOT_A_REAL_CODE", "nope")

    for code in jsonio.ERROR_CODES:
        assert jsonio.CommandError(code, "fine").code == code


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
