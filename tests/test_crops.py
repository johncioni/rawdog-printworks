import subprocess
from types import SimpleNamespace

import pytest

from pipeline import crops


def test_magick_cmd_native():
    cmd = crops.magick_cmd(
        "in.tif", "out.jpg", None, None, "0x0.8+0.6+0.008", 92, 300
    )
    assert "-crop" not in cmd and "-resize" not in cmd
    assert "-unsharp" in cmd and "92" in cmd
    assert cmd[-5:] == ["-colorspace", "sRGB", "-type", "TrueColor", "out.jpg"]


def test_magick_cmd_crop_and_resize():
    cmd = crops.magick_cmd(
        "in.tif",
        "out.jpg",
        {"x": 178, "y": 0, "w": 5420, "h": 4336},
        (3000, 2400),
        "0x1.0+0.8+0.01",
        92,
        300,
    )
    i = cmd.index("-crop")
    assert cmd[i + 1] == "5420x4336+178+0"
    assert cmd[cmd.index("-resize") + 1] == "3000x2400!"
    assert cmd.index("-crop") < cmd.index("-resize") < cmd.index("-unsharp")


def test_jpg_from_tif_runs_magick_command(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    crops.jpg_from_tif(
        "in.tif",
        "out.jpg",
        {"x": 178, "y": 0, "w": 5420, "h": 4336},
        (3000, 2400),
        "0x1.0+0.8+0.01",
        92,
        300,
    )

    expected = crops.magick_cmd(
        "in.tif",
        "out.jpg",
        {"x": 178, "y": 0, "w": 5420, "h": 4336},
        (3000, 2400),
        "0x1.0+0.8+0.01",
        92,
        300,
    )
    assert calls == [(expected, {"capture_output": True, "text": True})]


def test_jpg_from_tif_raises_crop_error_on_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stderr="specific magick failure")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(crops.CropError, match="specific magick failure"):
        crops.jpg_from_tif(
            "in.tif", "out.jpg", None, None, "0x0.8+0.6+0.008", 92, 300
        )
