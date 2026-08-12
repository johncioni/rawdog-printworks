import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from . import (crops, geometry, labprofile, manifest, metadata, paths, pdfs,
               publish, recipe, render, toolchain, verify as verify_mod)


LAB_PROFILE = "generic-v1"


def _lab():
    return labprofile.load(LAB_PROFILE)


def _lock():
    return json.loads((paths.config_dir() / "toolchain.lock").read_text())


def _current_fingerprint(stem):
    rec = recipe.load(stem)
    return recipe.fingerprint(
        stem,
        rec,
        render.style_hashes(stem),
        render.seed_hash(),
        _lock(),
        _lab(),
    )


def _dims(image):
    result = subprocess.run(
        ["magick", "identify", "-format", "%w %h", str(image)],
        capture_output=True,
        text=True,
    )
    fields = result.stdout.split()
    if result.returncode != 0 or len(fields) != 2:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"could not identify dimensions for {image}: {detail}")
    try:
        width, height = map(int, fields)
    except ValueError as error:
        raise RuntimeError(
            f"could not identify dimensions for {image}: {result.stdout!r}"
        ) from error
    if width <= 0 or height <= 0:
        raise RuntimeError(f"invalid render dimensions for {image}: {width}x{height}")
    return width, height


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_dims(rec):
    try:
        width, height = int(rec["render_width"]), int(rec["render_height"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("render dims not recorded; render first") from error
    if width <= 0 or height <= 0:
        raise ValueError("render dims not recorded; render first")
    return width, height


def _record_render_dims(stem, rec, width, height):
    if (abs(width - int(rec["width"])) > 16
            or abs(height - int(rec["height"])) > 16):
        raise RuntimeError(
            f"render dimensions {width}x{height} differ from declared "
            f"{rec['width']}x{rec['height']} by more than 16 pixels"
        )
    rec["render_width"] = width
    rec["render_height"] = height
    recipe.save(stem, rec)


def _crop_for(rec, crop, width, height, landscape, ppi):
    window = rec["crops"].get(crop)
    if window is None:
        window = geometry.centered_crop_norm(width, height, crop, landscape)
    geometry.validate_crop(
        window, width, height, crop, landscape, ppi
    )
    return window


def current_artifact_deps(stem):
    rec = recipe.load(stem)
    lab = _lab()
    lock = _lock()
    style_hashes = render.style_hashes(stem)
    seed_hash = render.seed_hash()
    try:
        width, height = _render_dims(rec)
    except ValueError:
        # The first render has not decoded the RAW yet. This geometry is used
        # only to establish that every artifact is stale; rendering records the
        # actual dimensions before any crop is produced or persisted.
        width, height = int(rec["width"]), int(rec["height"])
    landscape = width >= height
    dependencies = {}
    for name in manifest.artifact_names(stem):
        crop = next(
            (crop for crop in paths.CROPS if f"_{crop}." in name),
            None,
        )
        crop_geometry = None
        if crop is not None:
            crop_geometry = rec["crops"].get(crop)
            if crop_geometry is None:
                crop_geometry = geometry.centered_crop_norm(
                    width, height, crop, landscape
                )
        dependencies[name] = manifest.artifact_deps(
            stem,
            name,
            rec,
            style_hashes,
            seed_hash,
            lock,
            lab,
            crop_geometry,
        )
    return dependencies


def _reset_directory(directory):
    if directory.is_symlink() or directory.is_file():
        directory.unlink()
    elif directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def _published_current(stem):
    return paths.output_dir() / "photos" / stem / "current"


def _copy_published_artifacts(stem, staging):
    current = _published_current(stem)
    if not current.is_dir():
        return
    for name in manifest.artifact_names(stem):
        source = current / name
        if source.is_file():
            shutil.copy2(source, staging / name)


def _extract_comparison_source(stem, staging):
    pdf = staging / f"{stem}_comparison.pdf"
    if not pdf.is_file():
        raise RuntimeError(f"cannot recover comparison source: missing {pdf}")
    scratch = paths.run_dir() / f"comparison-source-{stem}"
    _reset_directory(scratch)
    try:
        prefix = scratch / "source"
        result = subprocess.run(
            ["pdfimages", "-j", str(pdf), str(prefix)],
            capture_output=True,
            text=True,
        )
        extracted = sorted(scratch.glob("source-*.jpg"))
        if result.returncode != 0 or len(extracted) != 1:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                "could not recover comparison source from published PDF: "
                f"{detail or f'{len(extracted)} JPEGs extracted'}"
            )
        shutil.copy2(extracted[0], staging / f"{stem}_comparison_src.jpg")
    finally:
        shutil.rmtree(scratch)


def _stage_published(stem):
    staging = paths.staging_dir() / f"{stem}.tmp"
    _reset_directory(staging)
    _copy_published_artifacts(stem, staging)
    missing = [
        name for name in manifest.artifact_names(stem)
        if not (staging / name).is_file()
    ]
    if missing:
        raise RuntimeError(
            f"published artifacts unavailable for {stem}: {', '.join(missing)}"
        )
    _extract_comparison_source(stem, staging)
    return staging


def render_photo(stem, only: set[str] | None = None):
    rec = recipe.load(stem)
    raw = render.resolve_raw(stem)
    actual_hash = _sha256(raw)
    if actual_hash != rec["raw_sha256"]:
        raise RuntimeError(
            f"archived RAW hash mismatch for {stem}: "
            f"expected {rec['raw_sha256']}, got {actual_hash}"
        )
    lab = _lab()

    all_names = set(manifest.artifact_names(stem))
    requested = all_names if only is None else set(only)
    unknown = requested - all_names
    if unknown:
        raise ValueError(f"unknown artifacts for {stem}: {sorted(unknown)}")

    staging = paths.staging_dir() / f"{stem}.tmp"
    _reset_directory(staging)
    if only is not None:
        _copy_published_artifacts(stem, staging)

    extra_profiles = (
        (render.denoise_profile(),)
        if rec["overrides"].get("denoise")
        else ()
    )
    rendered_styles = [
        style for style in paths.STYLES
        if any(
            name.startswith(f"{stem}_{style}.")
            or name.startswith(f"{stem}_{style}_")
            for name in requested
        )
    ]
    created_rasters = set()
    decoded_dims = None
    for style in rendered_styles:
        tif = staging / f"{stem}_{style}.tif"
        render.rt_render(
            raw,
            style,
            tif,
            "tif16",
            None,
            extra_profiles=extra_profiles,
        )
        width, height = _dims(tif)
        if decoded_dims is None:
            decoded_dims = (width, height)
            _record_render_dims(stem, rec, width, height)
        elif (width, height) != decoded_dims:
            raise RuntimeError(
                f"style TIF dimensions differ during render: "
                f"{decoded_dims[0]}x{decoded_dims[1]} vs {width}x{height}"
            )
        created_rasters.add(tif)

    width, height = decoded_dims or _render_dims(rec)
    landscape = width >= height
    native_jpgs = {}
    for style in paths.STYLES:
        tif = staging / f"{stem}_{style}.tif"
        native = staging / f"{stem}_{style}.jpg"
        native_jpgs[style] = native
        if native.name in requested:
            crops.jpg_from_tif(
                tif,
                native,
                None,
                None,
                rec["sharpen"]["native"],
                lab["jpeg_quality"],
                lab["ppi"],
            )
            created_rasters.add(native)
        for crop in paths.CROPS:
            output = staging / f"{stem}_{style}_{crop}.jpg"
            if output.name not in requested:
                continue
            normalized = _crop_for(
                rec, crop, width, height, landscape, lab["ppi"]
            )
            crops.jpg_from_tif(
                tif,
                output,
                geometry.to_pixels(normalized, width, height),
                geometry.target_pixels(crop, landscape, lab["ppi"]),
                rec["sharpen"][crop],
                lab["jpeg_quality"],
                lab["ppi"],
            )
            created_rasters.add(output)

    for raster in sorted(created_rasters):
        metadata.strip(raster, lab["keep_capture_date"])

    for style in paths.STYLES:
        for crop in (None, *paths.CROPS):
            suffix = "" if crop is None else f"_{crop}"
            jpg = staging / f"{stem}_{style}{suffix}.jpg"
            output = jpg.with_suffix(".pdf")
            if output.name not in requested:
                continue
            if crop is None:
                jpg_width, jpg_height = width, height
            else:
                jpg_width, jpg_height = geometry.target_pixels(
                    crop, landscape, lab["ppi"]
                )
            pdfs.wrap(
                jpg,
                output,
                geometry.pdf_page_inches(
                    crop, jpg_width, jpg_height, lab["ppi"], landscape
                ),
            )

    comparison = f"{stem}_comparison.pdf"
    if comparison in requested:
        pdfs.comparison_sheet(stem, native_jpgs, staging)
    else:
        complete = all((staging / name).is_file() for name in all_names)
        source = staging / f"{stem}_comparison_src.jpg"
        if complete and not source.is_file():
            _extract_comparison_source(stem, staging)
    return staging


def verify_photo(stem):
    staging = paths.staging_dir() / f"{stem}.tmp"
    names = manifest.artifact_names(stem)
    if not staging.is_dir():
        staging = _stage_published(stem)
    elif all((staging / name).is_file() for name in names):
        source = staging / f"{stem}_comparison_src.jpg"
        if not source.is_file():
            _extract_comparison_source(stem, staging)
    rec = recipe.load(stem)
    return verify_mod.photo(stem, staging, rec, _lab())


def approve(stem):
    rec = recipe.load(stem)
    if not rec.get("expression_audit"):
        raise RuntimeError("audit before approval")
    fingerprint = _current_fingerprint(stem)
    rec["approval"] = {
        "fingerprint": fingerprint,
        "approved_at": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
    }
    recipe.save(stem, rec)
    data = manifest.load()
    manifest.set_state(data, stem, "approved")
    data["photos"][stem]["fingerprint"] = fingerprint
    manifest.save(data)


def _publish_photo(stem):
    rec = recipe.load(stem)
    dependencies = current_artifact_deps(stem)
    provenance = {
        "fingerprint": _current_fingerprint(stem),
        "raw_sha256": rec["raw_sha256"],
        "toolchain": _lock(),
        "artifacts": dependencies,
    }
    publish.publish(
        stem,
        paths.staging_dir() / f"{stem}.tmp",
        provenance,
        set(manifest.artifact_names(stem)),
    )
    publish.rebuild_views()
    return dependencies


def _finish_verified(data, stem):
    problems = verify_photo(stem)
    if problems:
        print(f"{stem}: VERIFY FAILED\n  " + "\n  ".join(problems))
        return False
    dependencies = _publish_photo(stem)
    if isinstance(dependencies, dict):
        manifest.record_artifacts(data, stem, dependencies)
    manifest.set_state(data, stem, "verified")
    manifest.save(data)
    print(f"{stem}: verified and published")
    return True


def process_all():
    with publish.acquire_lock():
        tool_problems = toolchain.verify(paths.config_dir() / "toolchain.lock")
        publish.recover()
        publish.rebuild_views()

        hard_problems = [
            problem for problem in tool_problems
            if problem.get("name") not in toolchain.VERIFY_TOOLS
        ]
        if hard_problems:
            raise RuntimeError(
                f"toolchain drift, refusing to render: {hard_problems}"
            )

        data = manifest.load()
        if tool_problems:
            detail = "; ".join(
                f"{problem['name']}: {problem['problem']}"
                for problem in tool_problems
            )
            print(f"WARNING: verification tool drift; re-verifying: {detail}")
            changed = False
            for photo in data["photos"].values():
                if photo["state"] == "verified":
                    photo["state"] = "rendered"
                    changed = True
            if changed:
                manifest.save(data)

        for stem in sorted(data["photos"]):
            fingerprint = _current_fingerprint(stem)
            state = manifest.effective_state(data, stem, fingerprint)
            if state != data["photos"][stem]["state"]:
                manifest.set_state(data, stem, state)
                manifest.save(data)

            if state == "ingested":
                render.ensure_sidecar_all(stem)
                for style in paths.STYLES:
                    render.preview(stem, style)
                manifest.set_state(data, stem, "preview_ready")
                manifest.save(data)
                print(f"{stem}: previews ready — visual review required")
            elif state in ("preview_ready", "review_required"):
                print(f"{stem}: awaiting visual review + approve")
            elif state == "approved":
                stored = data["photos"][stem].get("artifacts", {})
                if not stored:
                    render_photo(stem)
                else:
                    current = current_artifact_deps(stem)
                    stale = set(manifest.stale_artifacts(
                        data, stem, current
                    ))
                    if stale == set(current):
                        render_photo(stem)
                    elif stale:
                        render_photo(stem, only=stale)
                _finish_verified(data, stem)
            elif state == "rendered":
                _finish_verified(data, stem)


def crop_preview(stem, style, crop):
    if style not in paths.STYLES:
        raise ValueError(f"unknown style: {style}")
    if crop not in paths.CROPS:
        raise ValueError(f"unknown crop: {crop}")
    staging = paths.staging_dir() / f"{stem}.tmp"
    tif = staging / f"{stem}_{style}.tif"
    if not tif.is_file():
        render_photo(stem, only={tif.name})

    rec = recipe.load(stem)
    try:
        width, height = _render_dims(rec)
    except ValueError:
        width, height = _dims(tif)
        _record_render_dims(stem, rec, width, height)
    lab = _lab()
    landscape = width >= height
    normalized = _crop_for(
        rec, crop, width, height, landscape, lab["ppi"]
    )
    output = paths.previews_dir() / f"{stem}_{style}_{crop}_croppreview.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)
    crops.jpg_from_tif(
        tif,
        output,
        geometry.to_pixels(normalized, width, height),
        geometry.target_pixels(crop, landscape, lab["ppi"]),
        rec["sharpen"][crop],
        lab["jpeg_quality"],
        lab["ppi"],
    )
    metadata.strip(output, lab["keep_capture_date"])
    return output
