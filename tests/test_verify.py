import subprocess
from pathlib import Path

from pipeline import pdfs, verify


SRGB_PROFILE = Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc")


def _jpg(directory, name="v.jpg"):
    path = directory / name
    subprocess.run(
        [
            "magick",
            "-size",
            "300x400",
            "xc:gray",
            "-depth",
            "8",
            "-profile",
            str(SRGB_PROFILE),
            "-density",
            "300",
            "-units",
            "PixelsPerInch",
            str(path),
        ],
        check=True,
    )
    return path


def test_image_pass(tmp_path):
    assert verify.check_image(
        _jpg(tmp_path), 300, 400, 8, 300, 10_000_000
    ) == []


def test_image_wrong_dims(tmp_path):
    problems = verify.check_image(
        _jpg(tmp_path), 999, 400, 8, 300, 10_000_000
    )
    assert any("dimensions" in problem for problem in problems)


def test_pdf_pass(tmp_path):
    staging = tmp_path / "staging"
    scratch = tmp_path / "scratch"
    staging.mkdir()
    scratch.mkdir()
    jpg = _jpg(staging)
    pdf = staging / "v.pdf"
    pdfs.wrap(jpg, pdf, (1.0, 400 / 300))

    assert verify.check_pdf(pdf, jpg, (72, 96), scratch) == []
    assert not list(staging.glob("extract*"))


def test_pdf_wrong_source(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    jpg = _jpg(tmp_path)
    other = _jpg(tmp_path, "other.jpg")
    subprocess.run(
        ["exiftool", "-overwrite_original", "-Comment=x", str(other)],
        check=True,
    )
    pdf = tmp_path / "v.pdf"
    pdfs.wrap(jpg, pdf, (1.0, 400 / 300))

    problems = verify.check_pdf(pdf, other, (72, 96), scratch)
    assert any("sha256" in problem.lower() for problem in problems)


def test_tif_exempt_from_size_cap(tmp_path):
    path = tmp_path / "big.tif"
    subprocess.run(
        [
            "magick",
            "-size",
            "300x400",
            "xc:gray",
            "-depth",
            "16",
            "-compress",
            "Zip",
            "-profile",
            str(SRGB_PROFILE),
            str(path),
        ],
        check=True,
    )
    assert verify.check_image(path, 300, 400, 16, 300, None) == []


def test_unexpected_file_detected(tmp_repo, monkeypatch):
    staging = tmp_repo / "staging" / "P1.tmp"
    staging.mkdir()
    (staging / "P1_comparison_src.jpg").write_bytes(b"source")
    (staging / "extract-000.jpg").write_bytes(b"rogue")
    monkeypatch.setattr(verify, "check_image", lambda *args: [])
    monkeypatch.setattr(verify, "check_pdf", lambda *args: [])

    problems = verify.photo(
        "P1",
        staging,
        {
            "width": 5776,
            "height": 4336,
            "render_width": 5784,
            "render_height": 4344,
        },
        {"ppi": 300, "max_file_bytes": 10_000_000,
         "keep_capture_date": True},
    )

    assert "unexpected file in staging: extract-000.jpg" in problems
    assert not (tmp_repo / "run" / "qa-P1").exists()
