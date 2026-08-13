import subprocess, sys

import pytest

from pipeline import __main__ as cli
from pipeline import driver


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
