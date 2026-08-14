import io
import json
import os
import subprocess, sys

import pytest

from pipeline import __main__ as cli
from pipeline import driver, jsonio


def test_cli_status_runs(tmp_repo):
    # Scoped to tmp_repo: without PIPELINE_ROOT the subprocess inherits the
    # developer environment and reads the live .manifest, archive/ and
    # recipes, making the result depend on gitignored photo data.
    p = subprocess.run([sys.executable, "-m", "pipeline", "status"],
                       capture_output=True, text=True,
                       env=dict(os.environ, PIPELINE_ROOT=str(tmp_repo)))
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
    """Capture the NDJSON stream of an in-process --json run. run_json now
    restores the stdout redirection itself, so this only has to reset the
    module state a prior test may have left."""
    buf = io.StringIO()
    monkeypatch.setattr(jsonio, "_out", None)
    monkeypatch.setattr(jsonio, "_real_stdout", lambda: buf)
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


def test_crops_json_returns_windows(tmp_repo, json_stream, monkeypatch):
    monkeypatch.setattr(driver, "crop_windows", lambda stem: {
        "stem": stem, "basis": "faces", "windows": {}})
    assert cli.main(["crops", "--stem", "P1", "--json"]) == 0
    assert _envelope(json_stream) == {
        "ok": True,
        "result": {"stem": "P1", "basis": "faces", "windows": {}}}


def test_crops_legacy_pretty_prints_result(tmp_repo, monkeypatch, capsys):
    monkeypatch.setattr(driver, "crop_windows", lambda stem: {
        "stem": stem, "basis": None, "windows": {}})
    assert cli.main(["crops", "--stem", "P1"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "stem": "P1", "basis": None, "windows": {}}


def test_crops_never_locks(tmp_repo):
    # Read-only: reporting crop windows must not contend for the driver mutex.
    p = _run(["crops", "--stem", "P1", "--json"], env=_held_lock_env(tmp_repo))
    envelope = json.loads(p.stdout.strip().splitlines()[-1])
    assert envelope["error"]["code"] == "NOT_FOUND"   # missing recipe, not lock


@pytest.fixture
def approve_calls(monkeypatch):
    calls = {"legacy": [], "review": []}
    monkeypatch.setattr(driver, "approve",
                        lambda stem: calls["legacy"].append(stem))
    monkeypatch.setattr(
        driver, "approve_review",
        lambda stem, review: calls["review"].append((stem, review))
        or {"stem": stem, "state": "approved", "fingerprint": "fp"})
    return calls


def _review_file(tmp_repo, body):
    path = tmp_repo / "review.json"
    path.write_text(body)
    return str(path)


def test_approve_review_file_json_is_the_canonical_spelling(
        tmp_repo, json_stream, approve_calls):
    review = {"expression_audit": ["ok"], "crops": {}}
    path = _review_file(tmp_repo, json.dumps(review))
    assert cli.main(["approve", "--stem", "P1", "--review-file", path,
                     "--json"]) == 0
    assert approve_calls["review"] == [("P1", review)]
    assert approve_calls["legacy"] == []
    assert _envelope(json_stream)["result"] == {
        "stem": "P1", "state": "approved", "fingerprint": "fp"}


def test_approve_without_review_file_stays_on_the_legacy_path(
        tmp_repo, approve_calls):
    assert cli.main(["approve", "P1"]) == 0
    assert approve_calls["legacy"] == ["P1"]
    assert approve_calls["review"] == []


def test_approve_review_file_legacy_mode_pretty_prints(
        tmp_repo, approve_calls, capsys):
    path = _review_file(tmp_repo, json.dumps({"expression_audit": ["ok"]}))
    assert cli.main(["approve", "P1", "--review-file", path]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "approved"


def test_approve_rejects_stem_given_twice(tmp_repo, approve_calls, capsys):
    assert cli.main(["approve", "P1", "--stem", "P1"]) == 1
    assert approve_calls["legacy"] == []
    assert "error:" in capsys.readouterr().err


def test_approve_malformed_review_file_is_bad_input(
        tmp_repo, json_stream, approve_calls):
    path = _review_file(tmp_repo, "{not json")
    assert cli.main(["approve", "--stem", "P1", "--review-file", path,
                     "--json"]) == 1
    assert _envelope(json_stream)["error"]["code"] == "BAD_INPUT"
    assert approve_calls["review"] == []


def test_approve_missing_review_file_is_not_found(
        tmp_repo, json_stream, approve_calls):
    assert cli.main(["approve", "--stem", "P1", "--review-file",
                     str(tmp_repo / "gone.json"), "--json"]) == 1
    assert _envelope(json_stream)["error"]["code"] == "NOT_FOUND"
    assert approve_calls["review"] == []


class _Calls(list):
    """A recording list that also carries the stub whose body tests set."""


@pytest.fixture
def run_calls(monkeypatch):
    """Record process_all's arguments; the body is supplied per test."""
    calls = _Calls()

    def fake_process_all(stems=None, force=False, collect=None):
        calls.append({"stems": stems, "force": force, "collect": collect})
        body = getattr(fake_process_all, "body", None)
        if body is not None:
            body(collect)

    monkeypatch.setattr(driver, "process_all", fake_process_all)
    calls.fake = fake_process_all
    return calls


def test_run_json_reports_collect_as_the_result(tmp_repo, json_stream,
                                                run_calls):
    def body(collect):
        collect["published"].append(
            {"stem": "P1", "version": "v004", "artifact_count": 29})
    run_calls.fake.body = body

    assert cli.main(["run", "--json"]) == 0

    assert _envelope(json_stream)["result"] == {
        "published": [{"stem": "P1", "version": "v004", "artifact_count": 29}],
        "advanced": [], "failed": []}


def test_run_json_forwards_stem_and_force(tmp_repo, json_stream, run_calls):
    assert cli.main(["run", "--stem", "P1", "--force", "--json"]) == 0
    assert run_calls[0]["stems"] == {"P1"}
    assert run_calls[0]["force"] is True
    assert run_calls[0]["collect"] is not None


def test_run_legacy_passes_no_scoping_and_no_collect(tmp_repo, run_calls):
    assert cli.main(["run"]) == 0
    assert run_calls == [{"stems": None, "force": False, "collect": None}]


def test_run_json_partial_failure_carries_successes(tmp_repo, json_stream,
                                                    run_calls):
    def body(collect):
        collect["published"].append(
            {"stem": "P1", "version": "v004", "artifact_count": 29})
        collect["failed"].append(
            {"stem": "P2", "code": "VERIFY_FAILED", "message": "bad pixels"})
    run_calls.fake.body = body

    assert cli.main(["run", "--json"]) == 1

    envelope = _envelope(json_stream)
    assert envelope["error"] == {"code": "PARTIAL_FAILURE",
                                 "message": "1 of 2 photos failed"}
    assert envelope["result"]["published"][0]["stem"] == "P1"


def test_run_json_toolchain_drift_is_toolchain_failed(tmp_repo, json_stream,
                                                      run_calls):
    def body(collect):
        raise RuntimeError("toolchain drift, refusing to render: [{}]")
    run_calls.fake.body = body

    assert cli.main(["run", "--json"]) == 1

    envelope = _envelope(json_stream)
    assert envelope["error"]["code"] == "TOOLCHAIN_FAILED"
    assert "toolchain drift" in envelope["error"]["message"]


def test_run_json_reports_held_lock(tmp_repo):
    # process_all takes the lock itself, so LOCK_HELD must survive the JSON
    # path rather than being swallowed as a toolchain failure.
    p = _run(["run", "--json"], env=_held_lock_env(tmp_repo))
    assert p.returncode == 1
    assert json.loads(p.stdout.strip().splitlines()[-1])["error"]["code"] == (
        "LOCK_HELD")
