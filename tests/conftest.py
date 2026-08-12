import pytest


@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    for d in ("Input", "Output", "archive", "staging", "run", "recipes",
              "sidecars", "previews", "config/lab-profiles", "config/styles",
              "config/rawtherapee-seed"):
        (tmp_path / d).mkdir(parents=True)
    monkeypatch.setenv("PIPELINE_ROOT", str(tmp_path))
    return tmp_path
