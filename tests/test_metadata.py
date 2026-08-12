import subprocess

from pipeline import metadata, toolchain


def _make_jpg(tmp_path):
    p = tmp_path / "t.jpg"
    subprocess.run(
        [
            "magick",
            "-size",
            "32x32",
            "xc:gray",
            "-profile",
            str(toolchain._rt_icc_path()),
            str(p),
        ],
        check=True,
    )
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-GPSLatitude=1.5",
            "-GPSLatitudeRef=N",
            "-Artist=Somebody",
            "-ISO=200",
            "-SerialNumber=ABC123",
            str(p),
        ],
        check=True,
    )
    return p


def test_strip_removes_private_keeps_allowed(tmp_path):
    p = _make_jpg(tmp_path)
    metadata.strip(p, keep_capture_date=True)
    out = subprocess.run(
        ["exiftool", "-j", "-G0", str(p)], capture_output=True, text=True
    ).stdout
    assert "GPS" not in out and "Somebody" not in out and "ABC123" not in out
    assert metadata.assert_clean(p, keep_capture_date=True) == []


def test_assert_flags_leftover_gps(tmp_path):
    p = _make_jpg(tmp_path)
    violations = metadata.assert_clean(p, keep_capture_date=True)
    assert any("GPS" in v for v in violations)


def test_strip_preserves_allowed_and_icc(tmp_path):
    p = _make_jpg(tmp_path)
    icc_before = subprocess.run(
        ["exiftool", "-icc_profile", "-b", str(p)],
        capture_output=True,
        check=True,
    ).stdout
    assert icc_before
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-DateTimeOriginal=2026:07:30 16:11:53",
            str(p),
        ],
        check=True,
    )
    metadata.strip(p, keep_capture_date=True)
    out = subprocess.run(
        ["exiftool", "-j", "-ISO", "-DateTimeOriginal", str(p)],
        capture_output=True,
        text=True,
    ).stdout
    assert "200" in out and "2026:07:30" in out
    icc_after = subprocess.run(
        ["exiftool", "-icc_profile", "-b", str(p)],
        capture_output=True,
        check=True,
    ).stdout
    assert icc_after == icc_before


def test_strip_drops_capture_date_when_configured(tmp_path):
    p = _make_jpg(tmp_path)
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-DateTimeOriginal=2026:07:30 16:11:53",
            str(p),
        ],
        check=True,
    )
    metadata.strip(p, keep_capture_date=False)
    out = subprocess.run(
        ["exiftool", "-j", "-DateTimeOriginal", str(p)],
        capture_output=True,
        text=True,
    ).stdout
    assert "2026:07:30" not in out
    assert metadata.assert_clean(p, keep_capture_date=False) == []


def test_strip_works_on_tif(tmp_path):
    p = tmp_path / "t.tif"
    subprocess.run(["magick", "-size", "32x32", "xc:gray", str(p)], check=True)
    subprocess.run(
        ["exiftool", "-overwrite_original", "-Artist=Somebody", str(p)],
        check=True,
    )
    metadata.strip(p, keep_capture_date=True)
    assert metadata.assert_clean(p, keep_capture_date=True) == []
