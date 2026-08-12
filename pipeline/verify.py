import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _identify(path):
    result = subprocess.run(
        [
            "magick",
            "identify",
            "-format",
            "%w %h %z %[colorspace]",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, result.stderr.strip()
    fields = result.stdout.split()
    if len(fields) != 4:
        return None, f"unexpected identify output: {result.stdout!r}"
    try:
        return (int(fields[0]), int(fields[1]), int(fields[2]), fields[3]), None
    except ValueError:
        return None, f"unexpected identify output: {result.stdout!r}"


def check_image(path, expect_w, expect_h, expect_bits, ppi, max_bytes):
    problems = []
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return [f"{path.name}: missing or empty"]

    size = path.stat().st_size
    if max_bytes is not None and size > max_bytes:
        problems.append(f"{path.name}: {size} bytes exceeds max {max_bytes}")

    identity, error = _identify(path)
    if error:
        problems.append(f"{path.name}: magick identify failed: {error}")
    else:
        width, height, bits, colorspace = identity
        if (width, height) != (expect_w, expect_h):
            problems.append(
                f"{path.name}: dimensions {width}x{height}, "
                f"expected {expect_w}x{expect_h}"
            )
        if bits != expect_bits:
            problems.append(
                f"{path.name}: bit depth {bits}, expected {expect_bits}"
            )
        if colorspace not in ("sRGB", "RGB"):
            problems.append(f"{path.name}: colorspace {colorspace}")

    meta_result = subprocess.run(
        [
            "exiftool",
            "-j",
            "-ICC_Profile:ProfileDescription",
            "-XResolution",
            "-YResolution",
            "-ResolutionUnit",
            "-Compression",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if meta_result.returncode != 0:
        problems.append(
            f"{path.name}: exiftool failed: {meta_result.stderr.strip()}"
        )
        return problems
    try:
        metadata = json.loads(meta_result.stdout)[0]
    except (IndexError, json.JSONDecodeError, TypeError):
        problems.append(
            f"{path.name}: unexpected exiftool output: {meta_result.stdout!r}"
        )
        return problems

    if "srgb" not in str(metadata.get("ProfileDescription", "")).casefold():
        problems.append(f"{path.name}: missing/non-sRGB ICC profile")

    suffix = path.suffix.casefold()
    if suffix in (".jpg", ".jpeg"):
        for tag in ("XResolution", "YResolution"):
            value = metadata.get(tag)
            try:
                matches = float(value) == float(ppi)
            except (TypeError, ValueError):
                matches = False
            if not matches:
                problems.append(
                    f"{path.name}: {tag} {value}, expected {ppi}"
                )
        unit = metadata.get("ResolutionUnit")
        if str(unit).casefold() != "inches":
            problems.append(
                f"{path.name}: ResolutionUnit {unit}, expected inches"
            )
    elif suffix in (".tif", ".tiff"):
        compression = metadata.get("Compression")
        if "deflate" not in str(compression).casefold():
            problems.append(
                f"{path.name}: Compression {compression}, expected Adobe Deflate"
            )

    return problems


def check_pdf(pdf, source_jpg, page_pts, scratch_dir):
    problems = []
    pdf = Path(pdf)
    source_jpg = Path(source_jpg)
    scratch_dir = Path(scratch_dir)
    if not pdf.exists() or pdf.stat().st_size == 0:
        return [f"{pdf.name}: missing or empty"]
    if not source_jpg.exists() or source_jpg.stat().st_size == 0:
        problems.append(f"{source_jpg.name}: missing or empty PDF source")

    qpdf = subprocess.run(
        ["qpdf", "--check", str(pdf)], capture_output=True, text=True
    )
    if qpdf.returncode != 0:
        problems.append(f"{pdf.name}: qpdf --check failed")

    listed = subprocess.run(
        ["pdfimages", "-list", str(pdf)], capture_output=True, text=True
    )
    listing = listed.stdout
    data_rows = [line for line in listing.splitlines()[2:] if line.strip()]
    if (listed.returncode != 0 or len(data_rows) != 1
            or " jpeg " not in f" {data_rows[0]} "):
        problems.append(
            f"{pdf.name}: expected exactly one embedded jpeg, got: {listing!r}"
        )

    scratch_dir.mkdir(parents=True, exist_ok=True)
    prefix = scratch_dir / f"extract_{pdf.stem}"
    for stale in scratch_dir.glob(f"{prefix.name}-*"):
        if stale.is_file() or stale.is_symlink():
            stale.unlink()
    extracted_result = subprocess.run(
        ["pdfimages", "-j", str(pdf), str(prefix)],
        capture_output=True,
        text=True,
    )
    extracted = sorted(scratch_dir.glob(f"{prefix.name}-*.jpg"))
    if (extracted_result.returncode != 0 or len(extracted) != 1
            or not source_jpg.exists()
            or _sha(extracted[0]) != _sha(source_jpg)):
        problems.append(f"{pdf.name}: embedded JPEG sha256 mismatch vs source")

    info_result = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True
    )
    info = info_result.stdout
    page_size = re.search(
        r"^Page size:\s+([\d.]+) x ([\d.]+) pts", info, re.MULTILINE
    )
    if (info_result.returncode != 0 or not page_size
            or (round(float(page_size.group(1))),
                round(float(page_size.group(2)))) != page_pts):
        problems.append(
            f"{pdf.name}: page size "
            f"{page_size and page_size.groups()}, expected {page_pts} pts"
        )
    for field in (
            "Title", "Author", "Subject", "Keywords",
            "Producer", "CreationDate", "ModDate"):
        match = re.search(rf"^{field}:\s*(.*)$", info, re.MULTILINE)
        if match and match.group(1).strip():
            problems.append(
                f"{pdf.name}: document info {field} is not empty"
            )

    return problems


def _recorded_render_dims(rec):
    try:
        width = rec["render_width"]
        height = rec["render_height"]
    except KeyError as error:
        raise ValueError("render dims not recorded; render first") from error
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError) as error:
        raise ValueError("render dims not recorded; render first") from error
    if width <= 0 or height <= 0:
        raise ValueError("render dims not recorded; render first")
    return width, height


def photo(stem, staging_dir, rec, lab):
    from . import geometry, labprofile, manifest, metadata, paths

    staging_dir = Path(staging_dir)
    native_width, native_height = _recorded_render_dims(rec)
    landscape = native_width >= native_height
    ppi, cap = lab["ppi"], lab["max_file_bytes"]
    names = manifest.artifact_names(stem)
    expected = set(names) | {f"{stem}_comparison_src.jpg"}
    actual = {path.name for path in staging_dir.iterdir()}
    problems = []
    for extra in sorted(actual - expected):
        problems.append(f"unexpected file in staging: {extra}")
    for missing in sorted(expected - actual):
        problems.append(f"missing artifact: {missing}")

    scratch = paths.run_dir() / f"qa-{stem}"
    if scratch.is_symlink() or scratch.is_file():
        scratch.unlink()
    elif scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)

    try:
        tif_dimensions = {}
        for style in paths.STYLES:
            name = f"{stem}_{style}.tif"
            path = staging_dir / name
            if not path.exists() or path.stat().st_size == 0:
                continue
            identity, _ = _identify(path)
            if identity is not None:
                tif_dimensions[name] = identity[:2]
        if len(set(tif_dimensions.values())) > 1:
            details = ", ".join(
                f"{name}={width}x{height}"
                for name, (width, height) in sorted(tif_dimensions.items())
            )
            problems.append(f"style TIF dimensions differ: {details}")

        for name in names:
            path = staging_dir / name
            if not path.exists():
                continue
            crop = next(
                (crop for crop in paths.CROPS if f"_{crop}." in name),
                None,
            )
            if name.endswith(".tif"):
                problems += check_image(
                    path,
                    native_width,
                    native_height,
                    16,
                    ppi,
                    None,
                )
                problems += [
                    f"{name}: metadata {violation}"
                    for violation in metadata.assert_clean(
                        path, lab["keep_capture_date"]
                    )
                ]
            elif name.endswith(".jpg"):
                width, height = (
                    geometry.target_pixels(crop, landscape, ppi)
                    if crop
                    else (native_width, native_height)
                )
                problems += check_image(
                    path, width, height, 8, ppi, cap
                )
                problems += [
                    f"{name}: metadata {violation}"
                    for violation in metadata.assert_clean(
                        path, lab["keep_capture_date"]
                    )
                ]
                filename_problem = labprofile.check_filename(name, lab)
                if filename_problem:
                    problems.append(filename_problem)
            elif name.endswith("_comparison.pdf"):
                problems += check_pdf(
                    path,
                    staging_dir / f"{stem}_comparison_src.jpg",
                    (792, 612),
                    scratch,
                )
            elif name.endswith(".pdf"):
                source = staging_dir / name.replace(".pdf", ".jpg")
                width, height = (
                    geometry.target_pixels(crop, landscape, ppi)
                    if crop
                    else (native_width, native_height)
                )
                page_width, page_height = geometry.pdf_page_inches(
                    crop, width, height, ppi, landscape
                )
                problems += check_pdf(
                    path,
                    source,
                    (round(page_width * 72), round(page_height * 72)),
                    scratch,
                )
        return problems
    finally:
        shutil.rmtree(scratch)
