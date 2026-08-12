import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import paths, render


def _successful_run(calls):
    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = kwargs.get("env")
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"out")
        return SimpleNamespace(returncode=0, stderr="")

    return fake_run


def test_rt_command_layers_profiles(tmp_repo, monkeypatch):
    (tmp_repo / "config/styles/natural.pp3").write_text("[Version]\n")
    (tmp_repo / "config/rawtherapee-seed/options").write_text("seed\n")
    (tmp_repo / "sidecars/P1_natural.pp3").write_text("[Exposure]\n")
    raw = tmp_repo / "Input/P1.rw2"
    raw.write_bytes(b"x")
    calls = {}
    monkeypatch.setattr(paths, "rt_cli", lambda: "/fake/rawtherapee-cli")
    monkeypatch.setattr(render.subprocess, "run", _successful_run(calls))

    render.rt_render(raw, "natural", tmp_repo / "staging/P1_natural.tif",
                     "tif16", None)

    cmd = calls["cmd"]
    p_indices = [i for i, arg in enumerate(cmd) if arg == "-p"]
    assert len(p_indices) == 2
    assert "natural.pp3" in cmd[p_indices[0] + 1]
    assert "P1_natural.pp3" in cmd[p_indices[1] + 1]
    assert "-b16" in cmd and "-tz" in cmd and "-d" not in cmd
    assert cmd[:5] == ["/fake/rawtherapee-cli", "-o",
                       str(tmp_repo / "staging/P1_natural.tif"), "-Y", "-q"]
    assert cmd[-2:] == ["-c", str(raw)]
    assert "RT_SETTINGS" in calls["env"] and "RT_CACHE" in calls["env"]
    assert "XDG_CONFIG_HOME" not in calls["env"]
    settings = Path(calls["env"]["RT_SETTINGS"])
    cache = Path(calls["env"]["RT_CACHE"])
    assert settings.parent == cache.parent
    assert settings.name == "settings" and cache.name == "cache"
    assert (settings / "options").read_text() == "seed\n"


def test_extra_profiles_between_base_and_sidecar(tmp_repo, monkeypatch):
    (tmp_repo / "config/styles/natural.pp3").write_text("[Version]\n")
    (tmp_repo / "sidecars/P1_natural.pp3").write_text("[Exposure]\n")
    raw = tmp_repo / "Input/P1.rw2"
    raw.write_bytes(b"x")
    calls = {}
    monkeypatch.setattr(paths, "rt_cli", lambda: "/fake/rawtherapee-cli")
    monkeypatch.setattr(render.subprocess, "run", _successful_run(calls))

    render.rt_render(raw, "natural", tmp_repo / "previews/P1.jpg", "jpg", 87,
                     extra_profiles=("/tmp/dn.pp3",))

    cmd = calls["cmd"]
    profiles = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-p"]
    assert profiles == [str(tmp_repo / "config/styles/natural.pp3"),
                        "/tmp/dn.pp3",
                        str(tmp_repo / "sidecars/P1_natural.pp3")]
    assert "-j87" in cmd and "-js3" in cmd


@pytest.mark.parametrize("returncode,create_output", [(1, True), (0, False)])
def test_rt_render_raises_on_failure_or_missing_output(
        tmp_repo, monkeypatch, returncode, create_output):
    (tmp_repo / "config/styles/natural.pp3").write_text("[Version]\n")
    raw = tmp_repo / "Input/P1.rw2"
    raw.write_bytes(b"x")
    monkeypatch.setattr(paths, "rt_cli", lambda: "/fake/rawtherapee-cli")

    def fake_run(cmd, **kwargs):
        if create_output:
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=returncode, stderr="specific failure")

    monkeypatch.setattr(render.subprocess, "run", fake_run)

    with pytest.raises(render.RenderError, match="specific failure"):
        render.rt_render(raw, "natural", tmp_repo / "staging/P1.tif",
                         "tif16", None)


def test_ensure_sidecar_creates_once(tmp_repo):
    sidecar = render.ensure_sidecar("P1", "natural")
    assert sidecar.exists()
    first = sidecar.read_text()
    assert render.ensure_sidecar("P1", "natural").read_text() == first


def test_ensure_sidecar_all_creates_every_style(tmp_repo):
    created = render.ensure_sidecar_all("P1")
    assert created == tuple(tmp_repo / "sidecars" / f"P1_{style}.pp3"
                            for style in paths.STYLES)
    assert all(sidecar.exists() for sidecar in created)


def test_preview_prefers_archive_and_falls_back_to_input(tmp_repo, monkeypatch):
    archived = tmp_repo / "archive/P1.rw2"
    input_raw = tmp_repo / "Input/P1.rw2"
    archived.write_bytes(b"archived")
    input_raw.write_bytes(b"input")
    calls = []

    def fake_render(raw, style, out_path, fmt, quality, extra_profiles=()):
        calls.append((raw, style, out_path, fmt, quality, extra_profiles))

    monkeypatch.setattr(render, "rt_render", fake_render)

    out = render.preview("P1", "natural")
    assert calls[-1][0] == archived
    assert out == tmp_repo / "previews/P1_natural_preview.jpg"
    archived.unlink()
    render.preview("P1", "filmic")
    assert calls[-1][0] == input_raw


def test_denoise_profile_is_written_once(tmp_repo):
    profile = render.denoise_profile()
    assert profile.parent == tmp_repo / "run"
    assert profile.read_text() == (
        "[Version]\nAppVersion=5.12\nVersion=352\n\n"
        "[Directional Pyramid Denoising]\nEnabled=true\n"
    )
    profile.write_text(profile.read_text() + "# keep\n")
    assert render.denoise_profile().read_text().endswith("# keep\n")


def test_style_hashes_include_only_matching_sidecars(tmp_repo):
    for style in paths.STYLES:
        (tmp_repo / f"config/styles/{style}.pp3").write_text(style)
    before = render.style_hashes("P1")
    (tmp_repo / "sidecars/P1_natural.pp3").write_text("override")
    after = render.style_hashes("P1")
    assert before["natural"] != after["natural"]
    assert before["filmic"] == after["filmic"]
    assert before["bw"] == after["bw"]


def test_seed_hash(tmp_repo):
    seed = tmp_repo / "config/rawtherapee-seed/options"
    assert render.seed_hash() == "no-seed"
    seed.write_bytes(b"seed")
    assert render.seed_hash() == hashlib.sha256(b"seed").hexdigest()
