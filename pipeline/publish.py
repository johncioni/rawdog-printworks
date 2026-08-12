import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

from . import paths


_VERSION_RE = re.compile(r"^v(\d{3,})$")
_VERSION_TMP_RE = re.compile(r"^v\d+\.tmp$")


class LockError(Exception):
    pass


def _lock_is_stale(lock):
    try:
        pid = int(lock.read_text().strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


@contextmanager
def acquire_lock():
    paths.run_dir().mkdir(parents=True, exist_ok=True)
    lock = paths.run_dir() / "driver.lock"
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if not _lock_is_stale(lock):
                raise LockError(f"another driver instance holds {lock}")
            try:
                lock.unlink()
            except FileNotFoundError:
                pass
            continue
        break

    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        lock.unlink(missing_ok=True)


def _photo_dir(stem):
    return paths.output_dir() / "photos" / stem


def _version_dirs(photo):
    versions = []
    if not photo.exists():
        return versions
    for candidate in photo.iterdir():
        match = _VERSION_RE.fullmatch(candidate.name)
        if match and candidate.is_dir():
            versions.append((int(match.group(1)), candidate))
    return sorted(versions)


def _next_version(photo):
    versions = _version_dirs(photo)
    number = versions[-1][0] + 1 if versions else 1
    while True:
        version = photo / f"v{number:03d}"
        temporary = photo / f"{version.name}.tmp"
        if version.exists():
            number += 1
            continue
        try:
            temporary.mkdir()
        except FileExistsError:
            number += 1
            continue
        return temporary, version


def _swap_current(photo, version_name):
    temporary = photo / f".current.tmp-{os.getpid()}"
    if temporary.is_symlink() or temporary.is_file():
        temporary.unlink()
    elif temporary.exists():
        shutil.rmtree(temporary)
    os.symlink(version_name, temporary)
    os.replace(temporary, photo / "current")


def _validate_allowlist(staging_dir, allowlist):
    names = set(allowlist)
    for name in names:
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"invalid publish allowlist entry: {name!r}")
        if name == "provenance.json":
            raise ValueError("provenance.json is generated during publish")
        source = staging_dir / name
        if not source.exists() and not source.is_symlink():
            raise FileNotFoundError(source)
    return names


def publish(stem, staging_dir, provenance, allowlist: set[str]) -> Path:
    staging_dir = Path(staging_dir)
    names = _validate_allowlist(staging_dir, allowlist)
    photo = _photo_dir(stem)
    photo.mkdir(parents=True, exist_ok=True)
    temporary, version = _next_version(photo)

    try:
        for name in sorted(names):
            os.rename(staging_dir / name, temporary / name)
        (temporary / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True)
        )
        os.rename(temporary, version)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    _swap_current(photo, version.name)
    for _, old in _version_dirs(photo):
        if old != version:
            shutil.rmtree(old)
    shutil.rmtree(staging_dir)
    return version


def _reset_directory(directory):
    if directory.is_symlink() or directory.is_file():
        directory.unlink()
    elif directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def rebuild_views():
    photos = paths.output_dir() / "photos"
    for view, extensions in (
        ("TIF", {".tif"}),
        ("JPG", {".jpg"}),
        ("PDF", {".pdf"}),
    ):
        view_dir = paths.output_dir() / view
        _reset_directory(view_dir)
        for photo in sorted(photos.glob("*")):
            current = photo / "current"
            if not current.is_symlink() or not current.is_dir():
                continue
            for artifact in sorted(current.iterdir()):
                if artifact.suffix.lower() not in extensions:
                    continue
                target = os.path.relpath(
                    photo / "current" / artifact.name,
                    view_dir,
                )
                os.symlink(target, view_dir / artifact.name)


def _remove_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _has_valid_provenance(version):
    try:
        provenance = json.loads((version / "provenance.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(provenance, dict)


def _publish_orphans(photo):
    orphans = []
    for candidate in sorted(photo.iterdir()):
        name = candidate.name
        if name.startswith(".current.tmp-") or (
            _VERSION_TMP_RE.fullmatch(name) and candidate.is_dir()
        ):
            orphans.append(candidate)
    return orphans


def _resolved_version(photo):
    """Name of the version directory `current` points at, or None."""
    current = photo / "current"
    if not current.is_symlink():
        return None
    target = os.readlink(current)
    if not _VERSION_RE.fullmatch(target):
        return None
    return target if (photo / target).is_dir() else None


def recover() -> list[str]:
    actions = []
    for orphan in sorted(paths.staging_dir().glob("*.tmp")):
        _remove_path(orphan)
        actions.append(f"removed orphan staging {orphan.name}")

    photos = paths.output_dir() / "photos"
    for photo in sorted(photos.glob("*")):
        if not photo.is_dir():
            continue
        for orphan in _publish_orphans(photo):
            _remove_path(orphan)
            actions.append(f"removed publish orphan {photo.name}/{orphan.name}")

        versions = [version for _, version in _version_dirs(photo)]
        current_target = _resolved_version(photo)
        if current_target is None:
            valid = [version for version in versions if _has_valid_provenance(version)]
            if len(valid) == 1:
                _swap_current(photo, valid[0].name)
                actions.append(
                    f"repointed {photo.name}/current to {valid[0].name}"
                )
                current_target = valid[0].name
            else:
                # Nothing trustworthy to prune against: leave the tree alone.
                if len(valid) > 1:
                    actions.append(
                        f"ambiguous versions for {photo.name}: manual attention "
                        f"needed — {', '.join(sorted(v.name for v in valid))}"
                    )
                continue

        for version in versions:
            if version.name != current_target:
                shutil.rmtree(version)
                actions.append(f"pruned {photo.name}/{version.name}")
    return actions
