import json
import subprocess


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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"exiftool strip failed: {result.stderr[-300:]}")


def assert_clean(path, keep_capture_date):
    allowed = ALLOWED - ({"DateTimeOriginal"} if not keep_capture_date else set())
    violations = []
    for group, name, value in _descriptive_tags(path):
        if name not in allowed:
            violations.append(f"{group}:{name}={value!r}")
    return violations
