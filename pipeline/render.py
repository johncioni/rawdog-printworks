import hashlib
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from . import paths


class RenderError(Exception):
    pass


def _isolated_env():
    run_dir = paths.run_dir() / f"rt-{uuid.uuid4().hex[:8]}"
    settings = run_dir / "settings"
    cache = run_dir / "cache"
    settings.mkdir(parents=True)
    cache.mkdir(parents=True)
    seed = paths.config_dir() / "rawtherapee-seed" / "options"
    if seed.exists():
        shutil.copy2(seed, settings / "options")
    return dict(os.environ, RT_SETTINGS=str(settings), RT_CACHE=str(cache))


def rt_render(raw, style, out_path, fmt, quality, extra_profiles=()):
    raw = Path(raw)
    out_path = Path(out_path)
    base = paths.config_dir() / "styles" / f"{style}.pp3"
    sidecar = paths.sidecars_dir() / f"{raw.stem}_{style}.pp3"
    cmd = [paths.rt_cli(), "-o", str(out_path), "-Y", "-q"]
    if fmt == "tif16":
        cmd += ["-b16", "-tz"]
    elif fmt == "jpg":
        cmd += [f"-j{quality or 92}", "-js3"]
    else:
        raise RenderError(f"unsupported RawTherapee output format: {fmt}")

    profiles = [base, *map(Path, extra_profiles)]
    if sidecar.exists():
        profiles.append(sidecar)
    for profile in profiles:
        cmd += ["-p", str(profile)]
    cmd += ["-c", str(raw)]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=_isolated_env())
    if result.returncode != 0 or not out_path.exists():
        stderr = result.stderr or ""
        raise RenderError(
            f"rawtherapee failed for {raw} [{style}]: {stderr[-500:]}")


def denoise_profile():
    profile = paths.run_dir() / "denoise.pp3"
    if not profile.exists():
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(
            "[Version]\n"
            "AppVersion=5.12\n"
            "Version=352\n\n"
            "[Directional Pyramid Denoising]\n"
            "Enabled=true\n"
        )
    return profile


def ensure_sidecar(stem, style):
    sidecar = paths.sidecars_dir() / f"{stem}_{style}.pp3"
    if not sidecar.exists():
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(
            f"# per-image override for {stem} [{style}] — layered over "
            f"config/styles/{style}.pp3\n"
        )
    return sidecar


def ensure_sidecar_all(stem):
    return tuple(ensure_sidecar(stem, style) for style in paths.STYLES)


def resolve_raw(stem):
    directories = (paths.archive_dir(), paths.input_dir())
    for directory in directories:
        if not directory.exists():
            continue
        for candidate in sorted(directory.iterdir()):
            if (candidate.is_file() and candidate.stem == stem
                    and candidate.suffix.lower() == ".rw2"):
                return candidate
    raise RenderError(
        f"RAW not found for stem {stem!r}; searched {directories[0]} and "
        f"{directories[1]}")


def preview(stem, style):
    raw = resolve_raw(stem)
    out = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
    rt_render(raw, style, out, "jpg", 92)
    return out


def _h(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def style_hashes(stem):
    hashes = {}
    for style in paths.STYLES:
        parts = _h(paths.config_dir() / "styles" / f"{style}.pp3")
        sidecar = paths.sidecars_dir() / f"{stem}_{style}.pp3"
        if sidecar.exists():
            parts += _h(sidecar)
        hashes[style] = hashlib.sha256(parts.encode()).hexdigest()
    return hashes


def seed_hash():
    seed = paths.config_dir() / "rawtherapee-seed" / "options"
    return _h(seed) if seed.exists() else "no-seed"
