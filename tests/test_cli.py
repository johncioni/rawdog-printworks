import io
import json
import os
import subprocess, sys

import pytest

from pipeline import __main__ as cli
from pipeline import driver, jsonio


def test_cli_status_runs():
    p = subprocess.run([sys.executable, "-m", "pipeline", "status"],
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert p.stdout.strip()


@pytest.fixture
def preview_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        driver, "preview_photo",
        lambda stem, style: calls.append((stem, style)) or f"/p/{stem}_{style}")
    return calls


@pytest.mark.parametrize("argv", [
    ["preview", "P1", "natural"],
    ["preview", "--stem", "P1", "--style", "natural"],
    ["preview", "P1", "--style", "natural"],
])
def test_cli_preview_accepts_positional_and_flag_forms(
        argv, preview_calls, capsys):
    assert cli.main(argv) == 0
    assert preview_calls == [("P1", "natural")]
    assert capsys.readouterr().out.strip() == "/p/P1_natural"


@pytest.mark.parametrize("argv", [
    ["preview", "P1"],
    ["preview", "--stem", "P1"],
    ["preview", "P1", "natural", "--stem", "P1"],
    ["preview", "P1", "natural", "--style", "natural"],
])
def test_cli_preview_rejects_missing_or_doubled_values(
        argv, preview_calls, capsys):
    assert cli.main(argv) == 1
    assert preview_calls == []
    assert "error:" in capsys.readouterr().err


def _run(args, env=None):
    return subprocess.run([sys.executable, "-m", "pipeline", *args],
                          capture_output=True, text=True, env=env)


def _held_lock_env(tmp_repo):
    """A lock file naming a live PID (ours) — never stale, so acquire fails."""
    (tmp_repo / "run").mkdir(exist_ok=True)
    (tmp_repo / "run/driver.lock").write_text(str(os.getpid()))
    return dict(os.environ, PIPELINE_ROOT=str(tmp_repo))


def test_mutating_command_reports_lock_held(tmp_repo):
    p = _run(["ingest", "--json"], env=_held_lock_env(tmp_repo))
    assert p.returncode == 1
    env_line = json.loads(p.stdout.strip().splitlines()[-1])
    assert env_line["ok"] is False
    assert env_line["error"]["code"] == "LOCK_HELD"


def test_status_never_locks(tmp_repo):
    p = _run(["status"], env=_held_lock_env(tmp_repo))
    assert p.returncode == 0        # legacy status works while lock held


def test_legacy_status_output_unchanged(tmp_repo):
    env = dict(os.environ, PIPELINE_ROOT=str(tmp_repo))
    p = _run(["status"], env=env)
    assert p.returncode == 0
    assert p.stdout == "photos: none ingested\n"


@pytest.fixture
def json_stream(monkeypatch):
    """Capture the NDJSON stream of an in-process --json run and undo the
    process-global stdout redirection jsonio.activate() installs."""
    buf = io.StringIO()
    monkeypatch.setattr(jsonio, "_out", None)
    monkeypatch.setattr(jsonio, "_real_stdout", lambda: buf)
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    return buf


def _envelope(buf):
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def test_verify_json_reports_problems_as_verify_failed(
        tmp_repo, json_stream, monkeypatch):
    monkeypatch.setattr(driver, "verify_photo",
                        lambda stem: ["tif missing", "dpi 240 != 300"])
    assert cli.main(["verify", "P1", "--json"]) == 1
    envelope = _envelope(json_stream)
    assert envelope["ok"] is False
    assert envelope["error"] == {"code": "VERIFY_FAILED",
                                 "message": "tif missing; dpi 240 != 300"}


def test_verify_json_reports_clean(tmp_repo, json_stream, monkeypatch):
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    assert cli.main(["verify", "P1", "--json"]) == 0
    assert _envelope(json_stream) == {
        "ok": True, "result": {"stem": "P1", "verify": "clean"}}


def test_legacy_verify_systemexit_releases_lock(tmp_repo, monkeypatch, capsys):
    # The legacy body exits with SystemExit — a BaseException — from inside
    # the dispatch lock; a leaked lock file would wedge every later command.
    monkeypatch.setattr(driver, "verify_photo", lambda stem: ["tif missing"])
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["verify", "P1"])
    assert exit_info.value.code == 1
    assert capsys.readouterr().out == "tif missing\n"
    assert not (tmp_repo / "run/driver.lock").exists()


@pytest.fixture
def preview_repo(tmp_repo, monkeypatch):
    import pathlib, shutil
    from pipeline import paths, recipe, toolchain
    for style in paths.STYLES:
        (tmp_repo / "config/styles" / f"{style}.pp3").write_text(f"# {style}\n")
    (tmp_repo / "config/toolchain.lock").write_text(json.dumps({}))
    source = pathlib.Path(__file__).resolve().parent.parent
    shutil.copy2(source / "config/lab-profiles/generic-v1.yaml",
                 tmp_repo / "config/lab-profiles/generic-v1.yaml")
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))

    def fake_preview(stem, style):
        path = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"rendered")
        return path
    monkeypatch.setattr(driver, "preview_photo", fake_preview)
    return tmp_repo


def test_preview_json_returns_adjust_shaped_result(preview_repo, json_stream):
    assert cli.main(["preview", "P1", "natural", "--json"]) == 0
    result = _envelope(json_stream)["result"]
    assert result["stem"] == "P1"
    assert result["style"] == "natural"
    assert result["preview"] == "previews/P1_natural_preview.jpg"
    assert result["temperature"] == {"value": None, "source": "camera"}
    # The revision is captured BEFORE the render, so writing the preview moves
    # it — a result reporting before == after would mean we sampled too late.
    assert result["review_revision_before"] != result["review_revision_after"]


def test_preview_json_unknown_stem_is_not_found(preview_repo, json_stream):
    assert cli.main(["preview", "NOPE", "natural", "--json"]) == 1
    assert _envelope(json_stream)["error"]["code"] == "NOT_FOUND"
