import subprocess


class CropError(Exception):
    pass


def magick_cmd(tif, out_jpg, crop_window, target, unsharp, quality, ppi):
    cmd = ["magick", str(tif)]
    if crop_window:
        window = crop_window
        cmd += [
            "-crop",
            f"{window['w']}x{window['h']}+{window['x']}+{window['y']}",
            "+repage",
        ]
    if target:
        cmd += ["-filter", "Lanczos", "-resize", f"{target[0]}x{target[1]}!"]
    cmd += [
        "-unsharp",
        unsharp,
        "-quality",
        str(quality),
        "-density",
        str(ppi),
        "-units",
        "PixelsPerInch",
        "-colorspace",
        "sRGB",
        "-type",
        "TrueColor",
        str(out_jpg),
    ]
    return cmd


def jpg_from_tif(tif, out_jpg, crop_window, target, unsharp, quality, ppi):
    result = subprocess.run(
        magick_cmd(tif, out_jpg, crop_window, target, unsharp, quality, ppi),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CropError(f"magick failed: {result.stderr[-500:]}")
