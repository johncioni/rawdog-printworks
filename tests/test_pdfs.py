import hashlib
import json
import subprocess

from pipeline import pdfs


def _jpg(tmp_path, name):
    path = tmp_path / name
    subprocess.run(
        [
            "magick",
            "-size",
            "300x400",
            "xc:gray",
            "-density",
            "300",
            "-units",
            "PixelsPerInch",
            str(path),
        ],
        check=True,
    )
    return path


def test_wrap_page_box(tmp_path):
    jpg = _jpg(tmp_path, "a.jpg")
    pdf = tmp_path / "a.pdf"
    pdfs.wrap(jpg, pdf, (8.0, 10.0))
    info = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True
    ).stdout
    assert "576 x 720" in info


def test_wrap_is_lossless(tmp_path):
    jpg = _jpg(tmp_path, "b.jpg")
    pdf = tmp_path / "b.pdf"
    pdfs.wrap(jpg, pdf, (8.0, 10.0))
    subprocess.run(
        ["pdfimages", "-j", str(pdf), str(tmp_path / "ex")], check=True
    )
    extracted = next(tmp_path.glob("ex-*.jpg"))
    assert hashlib.sha256(extracted.read_bytes()).hexdigest() == hashlib.sha256(
        jpg.read_bytes()
    ).hexdigest()


def test_wrap_clears_pdf_info_and_remains_qpdf_valid(tmp_path):
    jpg = _jpg(tmp_path, "clean.jpg")
    pdf = tmp_path / "clean.pdf"

    pdfs.wrap(jpg, pdf, (8.0, 10.0))

    info = subprocess.run(
        [
            "exiftool",
            "-j",
            "-PDF:Producer",
            "-PDF:CreationDate",
            "-PDF:ModDate",
            str(pdf),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tags = json.loads(info)[0]
    assert not tags.get("Producer")
    assert not tags.get("CreationDate")
    assert not tags.get("ModDate")
    checked = subprocess.run(
        ["qpdf", "--check", str(pdf)], capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stderr


def test_comparison_sheet_canvas_and_page(tmp_path):
    jpgs = {
        style: _jpg(tmp_path, f"{style}.jpg")
        for style in ("natural", "filmic", "bw", "vibrant")
    }
    pdf, src = pdfs.comparison_sheet("P1", jpgs, tmp_path)
    dims = subprocess.run(
        ["magick", "identify", "-format", "%w %h", str(src)],
        capture_output=True,
        text=True,
    ).stdout.split()
    assert dims == ["3300", "2550"]
    info = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True
    ).stdout
    assert "792 x 612" in info


def test_comparison_sheet_uses_four_labeled_panels_in_order(
        tmp_path, monkeypatch):
    jpgs = {
        style: tmp_path / f"{style}.jpg"
        for style in ("natural", "filmic", "bw", "vibrant")
    }
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        if cmd[0] == "magick":
            (tmp_path / cmd[-1]).write_bytes(b"image")

    wrapped = []

    def fake_wrap(source, output, page_inches):
        wrapped.append((source, output, page_inches))
        output.write_bytes(b"pdf")

    monkeypatch.setattr(pdfs, "_run", fake_run)
    monkeypatch.setattr(pdfs, "wrap", fake_wrap)

    pdf, src = pdfs.comparison_sheet("P1", jpgs, tmp_path)

    montage = calls[0]
    labeled = [
        (montage[index + 1], montage[index + 2])
        for index, argument in enumerate(montage)
        if argument == "-label"
    ]
    assert labeled == [
        (style, str(jpgs[style]))
        for style in ("natural", "filmic", "bw", "vibrant")
    ]
    assert montage[montage.index("-tile") + 1] == "4x1"
    assert montage[montage.index("-resize") + 1] == "750x"
    assert wrapped == [(src, pdf, (11.0, 8.5))]
