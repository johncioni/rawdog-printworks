import json
import shutil
import subprocess
from pathlib import Path


DESCRIPTIVE_GROUPS = {"EXIF", "XMP", "IPTC", "MakerNotes"}
STRUCTURAL_IMAGE_TAGS = {
    "ImageWidth",
    "ImageHeight",
    "BitsPerSample",
    "Compression",
    "PhotometricInterpretation",
    "Orientation",
    "SamplesPerPixel",
    "RowsPerStrip",
    "StripOffsets",
    "StripByteCounts",
    "MinSampleValue",
    "MaxSampleValue",
    "PlanarConfiguration",
    "XResolution",
    "YResolution",
    "ResolutionUnit",
    "SubfileType",
    # JPEG chroma structure, not descriptive metadata. exiftool materializes
    # YCbCrPositioning in IFD0 as a side effect of writing the resolution tags,
    # so omitting these makes every ppi-stamped JPG fail its own clean check.
    "YCbCrPositioning",
    "YCbCrSubSampling",
    "YCbCrCoefficients",
    # Mandatory EXIF block. Restoring any allowed EXIF tag makes exiftool
    # rebuild the ExifIFD, and a valid ExifIFD must carry these, so the strip
    # auto-creates them no matter what we ask for.
    "ExifVersion",
    "FlashpixVersion",
    "ComponentsConfiguration",
    "ColorSpace",
    "ExifImageWidth",
    "ExifImageHeight",
    "InteropIndex",
    "InteropVersion",
    # TIFF pixel layout. exiftool refuses to write or delete it ("doesn't
    # exist or isn't writable"), so every RawTherapee 16-bit TIF carries it
    # permanently and QA can never be satisfied by stripping it.
    "SampleFormat",
    # Decode-critical TIFF structure. These describe how the compressed bytes
    # map back to samples; deleting any of them leaves a file that still parses
    # but decodes to garbage. Predictor is the one that bit us: RawTherapee
    # writes deflate TIFs with horizontal differencing, and stripping the tag
    # made every master render embossed.
    "Predictor",
    "FillOrder",
    "TileWidth",
    "TileLength",
    "TileOffsets",
    "TileByteCounts",
    "FreeOffsets",
    "FreeByteCounts",
    "NewSubfileType",
}
ALLOWED = {
    "Orientation",
    "ExposureTime",
    "FNumber",
    "ISO",
    "FocalLength",
    "LensModel",
    "DateTimeOriginal",
    "Copyright",
    "XResolution",
    "YResolution",
    "ResolutionUnit",
}


def _descriptive_tags(path):
    output = subprocess.run(
        ["exiftool", "-j", "-G0:2", "-s", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tags = json.loads(output)[0]
    parsed = []
    for key, value in tags.items():
        parts = key.split(":", 2)
        if len(parts) != 3:
            continue
        group, category, name = parts
        if (group in DESCRIPTIVE_GROUPS
                and not (category == "Image"
                         and name in STRUCTURAL_IMAGE_TAGS)):
            parsed.append((group, name, value))
    return parsed


def _pixel_signature(path):
    """Hash of the decoded pixels, independent of the metadata around them."""
    result = subprocess.run(
        ["magick", str(path), "-format", "%#", "info:"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{path}: could not read pixels: {result.stderr.strip()[-300:]}"
        )
    return result.stdout.strip()


def strip(path, keep_capture_date, ppi=None):
    keep = ALLOWED - ({"DateTimeOriginal"} if not keep_capture_date else set())
    remove = {
        (group, name)
        for group, name, _ in _descriptive_tags(path)
        if name not in keep
    }
    cmd = [
        "exiftool",
        "-overwrite_original",
        "-all=",
        "--icc_profile:all",
        "-tagsfromfile",
        "@",
    ]
    cmd += [f"-EXIF:{tag}" for tag in sorted(keep)]
    if ppi is not None:
        cmd += [
            f"-EXIF:XResolution={ppi}",
            f"-EXIF:YResolution={ppi}",
            "-EXIF:ResolutionUnit=inches",
        ]
    cmd += [f"-{group}:{name}=" for group, name in sorted(remove)]
    cmd += [str(path)]

    # A metadata edit must never move a pixel. Deleting a decode-critical TIFF
    # tag corrupts the image while leaving a file that still opens, so the only
    # reliable check is the decoded output itself: hash it either side of the
    # rewrite and restore the original the moment the two disagree. Costs a few
    # seconds per TIF and turns silent corruption into a failure at the exact
    # point of introduction.
    target = Path(path)
    before = _pixel_signature(target)
    backup = target.parent / f".{target.name}.prestrip"
    shutil.copy2(target, backup)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"exiftool strip failed: {result.stderr[-300:]}")
        if _pixel_signature(target) != before:
            raise RuntimeError(
                f"{target}: strip changed decoded pixels — aborting"
            )
    except BaseException:
        shutil.move(backup, target)
        raise
    finally:
        backup.unlink(missing_ok=True)


def assert_clean(path, keep_capture_date):
    allowed = ALLOWED - ({"DateTimeOriginal"} if not keep_capture_date else set())
    violations = []
    for group, name, value in _descriptive_tags(path):
        if name not in allowed:
            violations.append(f"{group}:{name}={value!r}")
    return violations
