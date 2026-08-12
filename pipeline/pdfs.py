import os
import subprocess
import tempfile
from pathlib import Path


class PdfError(Exception):
    pass


_MACOS_HELVETICA = Path("/System/Library/Fonts/Helvetica.ttc")


def _run(cmd):
    env = None
    font_config = None
    if cmd[0] == "magick" and "Helvetica" in cmd and _MACOS_HELVETICA.exists():
        font_config = tempfile.TemporaryDirectory(prefix="photo-pipeline-font-")
        config_path = Path(font_config.name) / "type.xml"
        config_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<typemap>\n"
            '  <type name="Helvetica" fullname="Helvetica" family="Helvetica"\n'
            '        foundry="Apple" weight="400" style="normal" '
            'stretch="normal"\n'
            '        format="ttf" '
            f'metrics="{_MACOS_HELVETICA}" glyphs="{_MACOS_HELVETICA}"/>\n'
            "</typemap>\n"
        )
        env = os.environ.copy()
        config_dirs = [font_config.name]
        if existing := env.get("MAGICK_CONFIGURE_PATH"):
            config_dirs.append(existing)
        env["MAGICK_CONFIGURE_PATH"] = os.pathsep.join(config_dirs)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    finally:
        if font_config is not None:
            font_config.cleanup()
    if result.returncode != 0:
        raise PdfError(f"{cmd[0]} failed: {result.stderr[-400:]}")


def wrap(jpg, out_pdf, page_inches):
    width, height = page_inches
    _run(
        [
            "img2pdf",
            str(jpg),
            "--pagesize",
            f"{width}inx{height}in",
            "-o",
            str(out_pdf),
        ]
    )


def comparison_sheet(stem, native_jpgs, workdir):
    workdir = Path(workdir)
    tiles = workdir / f"{stem}_comparison_tiles.jpg"
    src = workdir / f"{stem}_comparison_src.jpg"
    _run(
        [
            "magick",
            "montage",
            "-font",
            "Helvetica",
            "-pointsize",
            "36",
            "-label",
            "natural",
            str(native_jpgs["natural"]),
            "-label",
            "filmic",
            str(native_jpgs["filmic"]),
            "-label",
            "bw",
            str(native_jpgs["bw"]),
            "-tile",
            "3x1",
            "-resize",
            "1000x",
            "-geometry",
            "+20+40",
            "-background",
            "white",
            str(tiles),
        ]
    )
    _run(
        [
            "magick",
            str(tiles),
            "-background",
            "white",
            "-gravity",
            "center",
            "-extent",
            "3300x2550",
            "-density",
            "300",
            "-units",
            "PixelsPerInch",
            "-quality",
            "92",
            str(src),
        ]
    )
    tiles.unlink()
    pdf = workdir / f"{stem}_comparison.pdf"
    wrap(src, pdf, (11.0, 8.5))
    return pdf, src
