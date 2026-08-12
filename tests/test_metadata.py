import json
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


def test_strip_tolerates_the_exif_block_it_rebuilds(tmp_path):
    """Restoring any allowed EXIF tag makes exiftool rebuild the ExifIFD.

    A valid ExifIFD is required to carry the mandatory block (ExifVersion,
    ComponentsConfiguration, ColorSpace), so the strip auto-creates tags it
    never asked for. test_strip_works_on_tif misses this: a bare TIF has no
    allowed EXIF tag to restore, so no ExifIFD is ever built.
    """
    p = tmp_path / "rebuilt.tif"
    subprocess.run(
        ["magick", "-size", "32x32", "xc:gray", "-depth", "16", "-type",
         "TrueColor", str(p)],
        check=True,
    )
    subprocess.run(
        ["exiftool", "-overwrite_original", "-ISO=200",
         "-DateTimeOriginal=2026:07:30 16:11:53", "-Artist=Somebody", str(p)],
        check=True,
    )
    # Writing those tags creates the mandatory block as a side effect. Clear it
    # so the fixture matches a fresh RawTherapee render, which carries the
    # allowed tags without the block; leaving it in makes strip() name it for
    # deletion and the auto-creation never shows.
    subprocess.run(
        ["exiftool", "-overwrite_original", "-EXIF:ExifVersion=",
         "-EXIF:ComponentsConfiguration=", "-EXIF:ColorSpace=", str(p)],
        check=True,
    )

    metadata.strip(p, keep_capture_date=True)

    assert metadata.assert_clean(p, keep_capture_date=True) == []
    out = subprocess.run(
        ["exiftool", "-j", "-ISO", "-Artist", str(p)],
        capture_output=True, text=True, check=True,
    ).stdout
    tags = json.loads(out)[0]
    assert tags["ISO"] == 200
    assert "Artist" not in tags


def test_tif_image_category_only_exempts_structural_tags(tmp_path):
    p = tmp_path / "descriptive.tif"
    subprocess.run(
        ["magick", "-size", "32x32", "xc:red", "-type", "TrueColor", str(p)],
        check=True,
    )
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-Software=Leaky Software",
            "-ImageDescription=Leaky Description",
            str(p),
        ],
        check=True,
    )

    violations = metadata.assert_clean(p, keep_capture_date=True)
    assert any("EXIF:Software" in violation for violation in violations)
    assert any("EXIF:ImageDescription" in violation for violation in violations)

    metadata.strip(p, keep_capture_date=True)

    out = subprocess.run(
        ["exiftool", "-j", "-Software", "-ImageDescription", str(p)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tags = json.loads(out)[0]
    assert "Software" not in tags
    assert "ImageDescription" not in tags
    assert metadata.assert_clean(p, keep_capture_date=True) == []


def test_image_category_structural_allowlist_is_exact():
    assert metadata.STRUCTURAL_IMAGE_TAGS == {
        "ImageWidth", "ImageHeight", "BitsPerSample", "Compression",
        "PhotometricInterpretation", "Orientation", "SamplesPerPixel",
        "RowsPerStrip", "StripOffsets", "StripByteCounts", "MinSampleValue",
        "MaxSampleValue", "PlanarConfiguration", "XResolution",
        "YResolution", "ResolutionUnit", "SubfileType",
        "YCbCrPositioning", "YCbCrSubSampling", "YCbCrCoefficients",
        "ExifVersion", "FlashpixVersion", "ComponentsConfiguration",
        "ColorSpace", "ExifImageWidth", "ExifImageHeight", "InteropIndex",
        "InteropVersion", "SampleFormat",
    }


def test_strip_sets_jpg_resolution_when_ppi_is_provided(tmp_path):
    p = tmp_path / "resolution.jpg"
    subprocess.run(
        [
            "magick",
            "-size",
            "32x32",
            "xc:gray",
            "-density",
            "300",
            "-units",
            "PixelsPerInch",
            str(p),
        ],
        check=True,
    )

    metadata.strip(p, keep_capture_date=True, ppi=300)

    out = subprocess.run(
        [
            "exiftool",
            "-j",
            "-EXIF:XResolution",
            "-EXIF:YResolution",
            "-EXIF:ResolutionUnit",
            str(p),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tags = json.loads(out)[0]
    assert tags["XResolution"] == 300
    assert tags["YResolution"] == 300
    assert tags["ResolutionUnit"] == "inches"
    # Writing the resolution tags makes exiftool materialize the IFD0 chroma
    # companions, so the strip must leave the JPG clean rather than reintroduce
    # a violation QA then rejects.
    assert metadata.assert_clean(p, keep_capture_date=True) == []
