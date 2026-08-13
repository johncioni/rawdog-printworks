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
