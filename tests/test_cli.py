import subprocess, sys


def test_cli_status_runs():
    p = subprocess.run([sys.executable, "-m", "pipeline", "status"],
                       capture_output=True, text=True)
    assert p.returncode == 0
    assert "photos" in p.stdout.lower()
