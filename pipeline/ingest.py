import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from . import manifest, paths, recipe


class IngestError(Exception):
    pass


EXPECTED = {"Make": "Panasonic", "Model": "DC-GH7"}
_KEYS = ("Make", "Model", "ImageWidth", "ImageHeight", "Orientation",
         "LensModel", "ISO", "ExposureTime", "AspectRatio")
_ORIENTATIONS = {
    "Horizontal (normal)",
    "Mirror horizontal",
    "Rotate 180",
    "Mirror vertical",
    "Mirror horizontal and rotate 270 CW",
    "Rotate 90 CW",
    "Mirror horizontal and rotate 90 CW",
    "Rotate 270 CW",
}


def exif_summary(path):
    path = Path(path)
    try:
        completed = subprocess.run(
            ["exiftool", "-j", *[f"-{key}" for key in _KEYS], str(path)],
            capture_output=True, text=True, check=True)
        payload = json.loads(completed.stdout)
        if not isinstance(payload, list) or not payload:
            raise ValueError("no metadata record returned")
        meta = payload[0]
        if not isinstance(meta, dict):
            raise ValueError("metadata record is not an object")
        return meta
    except (OSError, subprocess.SubprocessError, ValueError, TypeError,
            IndexError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        if isinstance(detail, str):
            detail = detail.strip()
        raise IngestError(
            f"{path.stem}: unreadable metadata: {detail}") from error


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_dimension(value):
    return (not isinstance(value, bool)
            and isinstance(value, (int, float))
            and value > 0)


def _preflight(path, existing_stems, existing_hashes, src_sha=None):
    stem = Path(path).stem
    if stem in existing_stems:
        raise IngestError(
            f"duplicate stem {stem}: needs explicit user confirmation")
    if src_sha is not None and src_sha in existing_hashes:
        raise IngestError(f"{stem}: duplicate content already archived")

    meta = exif_summary(path)
    if (not _valid_dimension(meta.get("ImageWidth"))
            or not _valid_dimension(meta.get("ImageHeight"))):
        raise IngestError(f"{stem}: unreadable dimensions")

    warnings = []
    for key, expected in EXPECTED.items():
        if meta.get(key) != expected:
            warnings.append(
                f"{stem}: unexpected {key} {meta.get(key)!r} "
                f"(expected {expected!r})")

    iso = meta.get("ISO")
    try:
        high_iso = not isinstance(iso, bool) and float(iso) > 1600
    except (TypeError, ValueError):
        high_iso = False
    if high_iso:
        warnings.append(
            f"{stem}: high ISO {iso} — consider per-image denoise override")

    orientation = meta.get("Orientation")
    if orientation not in _ORIENTATIONS:
        warnings.append(f"{stem}: unrecognized Orientation {orientation!r}")
    return warnings, meta


def preflight(path, existing_stems, existing_hashes):
    return _preflight(path, existing_stems, existing_hashes)


def preflight_with_hash(path, existing_stems, existing_hashes, src_sha):
    return _preflight(path, existing_stems, existing_hashes, src_sha)


def archive(path, src_sha):
    path = Path(path)
    destination = paths.archive_dir() / path.name
    if destination.exists():
        raise IngestError(f"{path.name}: archive destination already exists")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    if _sha256(destination) != src_sha:
        destination.unlink()
        raise IngestError(f"{path.name}: archive copy hash mismatch")

    with open(paths.archive_dir() / "SHA256SUMS", "a", encoding="utf-8") as sums:
        sums.write(f"{src_sha}  {path.name}\n")


def _archived_hashes():
    sums = paths.archive_dir() / "SHA256SUMS"
    if not sums.exists():
        return set()
    return {line.split()[0] for line in sums.read_text().splitlines()
            if line.strip()}


def run():
    manifest_data = manifest.load()
    results = {}
    existing_hashes = _archived_hashes()
    for raw in sorted(paths.input_dir().glob("*.rw2")):
        stem = raw.stem
        try:
            if stem in manifest_data["photos"]:
                results[stem] = "skipped (already ingested)"
                continue
            src_sha = _sha256(raw)
            warnings, meta = preflight_with_hash(
                raw, set(manifest_data["photos"]), existing_hashes, src_sha)
            for warning in warnings:
                print(f"WARNING: {warning}")
            archive(raw, src_sha)
            existing_hashes.add(src_sha)
            recipe.save(stem, recipe.new(
                stem, src_sha, meta["ImageWidth"], meta["ImageHeight"]))
            manifest.set_state(manifest_data, stem, "ingested")
            results[stem] = "ok"
        except (IngestError, OSError) as error:
            results[stem] = f"failed: {error}"
            print(f"FAILED {stem}: {error}")
    manifest.save(manifest_data)
    return results
