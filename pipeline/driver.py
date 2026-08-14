import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import (crops, geometry, jsonio, labprofile, manifest, metadata, paths,
               pdfs, provenance, publish, recipe, render, subject, toolchain,
               verify as verify_mod)


LAB_PROFILE = "generic-v1"
MANUAL_ASSETS_ERROR = "manual assets present; outside automated re-render"


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


def preview_photo(stem, style):
    if style not in paths.STYLES:
        raise ValueError(f"unknown style: {style}")
    rec = recipe.load(stem)
    raw = render.resolve_raw(stem)
    actual_hash = _sha256(raw)
    if actual_hash != rec["raw_sha256"]:
        raise RuntimeError(
            f"archived RAW hash mismatch for {stem}: "
            f"expected {rec['raw_sha256']}, got {actual_hash}")
    material = provenance.gather_material(stem)
    inputs_hash = provenance.style_input_hash(stem, style, rec, material)

    final = paths.previews_dir() / f"{stem}_{style}_preview.jpg"
    tmp = paths.run_dir() / f"preview-{stem}-{style}.tmp.jpg"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.unlink(missing_ok=True)
    extra = ((render.denoise_profile(),)
             if rec["overrides"].get("denoise") else ())
    render.rt_render(raw, style, tmp, "jpg", 92, extra_profiles=extra)

    # Inputs must be identical before AND after the render, or the recorded
    # provenance would describe profiles that weren't the ones rendered.
    post_hash = provenance.style_input_hash(
        stem, style, rec, provenance.gather_material(stem))
    if post_hash != inputs_hash:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"render inputs changed during preview render for {stem} "
            f"[{style}]; re-run")

    # Validate the temp ALWAYS; a failure here leaves preview + recipe alone.
    width, height = _dims(tmp)
    if (abs(width - int(rec["width"])) > 16
            or abs(height - int(rec["height"])) > 16):
        raise RuntimeError(
            f"render dimensions {width}x{height} differ from declared "
            f"{rec['width']}x{rec['height']} by more than 16 pixels")
    try:
        _render_dims(rec)
    except ValueError:
        rec["render_width"], rec["render_height"] = width, height
    provenance.record_preview(rec, stem, style, tmp, inputs_hash)

    # Recipe first, swap second: a save failure changes nothing on disk; a
    # crash between the two leaves a hash mismatch that reads as STALE, not
    # as falsely fresh.
    recipe.save(stem, rec)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, final)
    return final


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


def _stage_event(stem, stage):
    jsonio.emit({"event": "stage", "stem": stem, "stage": stage})


class _RenderProgress:
    """1-based progress counter over the artifacts a render was asked for."""

    def __init__(self, stem, total):
        self.stem = stem
        self.total = total
        self.index = 0

    def landed(self, name):
        self.index += 1
        jsonio.emit({"event": "progress", "stem": self.stem,
                     "stage": "render", "index": self.index,
                     "total": self.total, "detail": name})


def render_photo(stem, only: set[str] | None = None):
    rec = recipe.load(stem)
    if rec.get("manual_assets"):
        raise RuntimeError(MANUAL_ASSETS_ERROR)
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
    progress = _RenderProgress(stem, len(requested))
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
        # A style TIF can be a dependency of a requested JPG without being
        # requested itself, and only requested names are counted.
        if tif.name in requested:
            progress.landed(tif.name)

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
            progress.landed(native.name)
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
            progress.landed(output.name)

    for raster in sorted(created_rasters):
        ppi = lab["ppi"] if raster.suffix.lower() == ".jpg" else None
        metadata.strip(raster, lab["keep_capture_date"], ppi=ppi)

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
            progress.landed(output.name)

    comparison = f"{stem}_comparison.pdf"
    if comparison in requested:
        pdfs.comparison_sheet(stem, native_jpgs, staging)
        progress.landed(comparison)
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


def crop_windows(stem):
    """Report the crop windows `approve` would bind, without binding them.

    `basis` describes the suggestion path only; a fully persisted recipe
    suggests nothing, so its basis is None and each window says so itself.
    """
    rec = recipe.load(stem)
    persisted = {c: w for c, w in rec["crops"].items() if w is not None}
    if len(persisted) == len(paths.CROPS):
        return {"stem": stem, "basis": None,
                "windows": {c: dict(w, source="persisted")
                            for c, w in persisted.items()}}
    try:
        width, height = _render_dims(rec)
    except ValueError as error:
        raise jsonio.CommandError(
            "BAD_INPUT", "render dims not recorded; generate previews first"
        ) from error
    landscape = width >= height
    preview = paths.previews_dir() / f"{stem}_natural_preview.jpg"
    if preview.is_file():
        bbox, basis = subject.group_bbox_detail(preview)
        if basis == "no_faces":
            basis = "center"
    else:
        bbox, basis = None, "center"
    windows = {}
    for crop in paths.CROPS:
        if crop in persisted:
            windows[crop] = dict(persisted[crop], source="persisted")
            continue
        if bbox is None:
            window = geometry.centered_crop_norm(width, height, crop, landscape)
        else:
            window = geometry.subject_crop_norm(width, height, crop,
                                                landscape, bbox)
        windows[crop] = dict(window, source="suggested")
    return {"stem": stem, "basis": basis, "windows": windows}


def _review_windows(windows):
    """Normalize submitted crop windows down to geometry alone.

    The app echoes back the windows `crops` reported, which carry a `source`
    tag; persisting that would make recipe.fingerprint reject the recipe as
    non-numeric geometry long after the input was accepted.
    """
    if not isinstance(windows, dict):
        raise jsonio.CommandError("BAD_INPUT", "crops must be an object")
    keys = ("x", "y", "w", "h")
    normalized = {}
    for crop, window in windows.items():
        if not isinstance(window, dict):
            raise jsonio.CommandError(
                "BAD_INPUT", f"invalid {crop} window: expected an object")
        fields = {k: v for k, v in window.items() if k in keys}
        for k, v in fields.items():
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise jsonio.CommandError(
                    "BAD_INPUT", f"invalid {crop} window: {k} is not a number")
        normalized[crop] = fields
    return normalized


def approve_review(stem, review):
    audit = review.get("expression_audit")
    if (not isinstance(audit, list) or not audit
            or not all(isinstance(item, str) for item in audit)):
        raise jsonio.CommandError(
            "BAD_INPUT", "expression_audit must be a non-empty list of strings")
    windows = _review_windows(review.get("crops") or {})
    missing = [c for c in paths.CROPS if c not in windows]
    if missing:
        raise jsonio.CommandError(
            "BAD_INPUT", f"crops missing windows: {missing}")

    # THE single snapshot: one recipe load + one material gather; revision,
    # staleness, and the final fingerprint all derive from these same reads,
    # so an edit between "check" and "persist" cannot enter the fingerprint
    # without having entered the checked revision.
    rec = recipe.load(stem)
    material = provenance.gather_material(stem)
    expected = review.get("expected_review_revision")
    if expected is not None:
        current = provenance.review_revision(stem, rec, material)
        if expected != current:
            raise jsonio.CommandError(
                "STALE_REVIEW",
                "review inputs changed since the reviewed snapshot")
        stale = provenance.stale_styles(stem, rec, material)
        if stale:
            raise jsonio.CommandError(
                "STALE_REVIEW", f"previews stale for styles: {stale}")

    try:
        width, height = _render_dims(rec)
    except ValueError as error:
        raise jsonio.CommandError("BAD_INPUT", str(error)) from error
    landscape = width >= height
    lab = material["lab"]
    for crop, window in windows.items():
        try:
            geometry.validate_crop(window, width, height, crop, landscape,
                                   lab["ppi"])
        except Exception as error:
            raise jsonio.CommandError(
                "BAD_INPUT", f"invalid {crop} window: {error}") from error

    rec["crops"] = {c: dict(windows[c]) for c in paths.CROPS}
    rec["expression_audit"] = list(audit)
    fingerprint = recipe.fingerprint(stem, rec, material["style_hashes"],
                                     material["seed_hash"], material["lock"],
                                     material["lab"])
    rec["approval"] = {
        "fingerprint": fingerprint,
        "approved_at": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
    }
    recipe.save(stem, rec)
    data = manifest.load()
    manifest.set_state(data, stem, "approved")
    data["photos"][stem]["fingerprint"] = fingerprint
    manifest.save(data)
    return {"stem": stem, "state": "approved", "fingerprint": fingerprint}


def approve(stem):
    rec = recipe.load(stem)
    if not rec.get("expression_audit"):
        raise RuntimeError("audit before approval")
    default_crops = [
        crop for crop in paths.CROPS if rec["crops"].get(crop) is None
    ]
    if default_crops:
        try:
            width, height = _render_dims(rec)
        except ValueError as error:
            raise RuntimeError(
                "render dims not recorded; run croppreview/preview first"
            ) from error
        landscape = width >= height
        preview = paths.previews_dir() / f"{stem}_natural_preview.jpg"
        bbox = None
        if preview.is_file():
            bbox = subject.group_bbox(preview)
        else:
            print(
                f"NOTE: {stem}: natural preview missing; "
                "using geometric center"
            )
        for crop in default_crops:
            if bbox is None:
                window = geometry.centered_crop_norm(
                    width, height, crop, landscape
                )
            else:
                window = geometry.subject_crop_norm(
                    width, height, crop, landscape, bbox
                )
                if bbox["w"] > window["w"] or bbox["h"] > window["h"]:
                    print(
                        f"WARNING: {stem} {crop}: group extends beyond "
                        "crop window — review before approving"
                    )
            rec["crops"][crop] = window
        # Approval must bind the materialized geometry, not an implicit default
        # that could change independently of the persisted recipe.
        recipe.save(stem, rec)
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


def _published_version(stem):
    """Version `current` points at, or None if nothing is published yet."""
    current = _published_current(stem)
    if not current.is_symlink():
        return None
    return os.path.basename(os.readlink(current))


def _finish_verified(data, stem, collect=None):
    _stage_event(stem, "verify")
    problems = verify_photo(stem)
    if problems:
        print(f"{stem}: VERIFY FAILED\n  " + "\n  ".join(problems))
        if collect is not None:
            collect.setdefault("failed", []).append(
                {"stem": stem, "code": "VERIFY_FAILED",
                 "message": "; ".join(problems)})
        return False
    _stage_event(stem, "publish")
    dependencies = _publish_photo(stem)
    if isinstance(dependencies, dict):
        manifest.record_artifacts(data, stem, dependencies)
    manifest.set_state(data, stem, "verified")
    manifest.save(data)
    print(f"{stem}: verified and published")
    if collect is not None:
        collect.setdefault("published", []).append(
            {"stem": stem, "version": _published_version(stem),
             "artifact_count": len(dependencies or {})})
    return True


def _selected_stems(data, stems, collect):
    if stems is None:
        return sorted(data["photos"])
    requested, known = set(stems), set(data["photos"])
    if collect is not None:
        for stem in sorted(requested - known):
            collect["failed"].append(
                {"stem": stem, "code": "NOT_FOUND",
                 "message": f"no photo named {stem} in the manifest"})
    else:
        # Legacy `run` has no failure contract for an unknown stem, so a typo
        # must still be visible rather than exiting 0 having done nothing.
        for stem in sorted(requested - known):
            print(f"WARNING: unknown stem {stem} — skipped")
    return sorted(requested & known)


_UNSET = object()


def _force_downgrade(data, stem):
    """Reset a stem to `approved` in memory so the normal flow re-renders it.

    Nothing is saved here: the downgrade reaches the manifest only when
    `_finish_verified` persists the new version, so a failed forced run leaves
    the manifest describing the version still in the published tree.
    """
    photo = data["photos"][stem]
    remembered = (photo["state"], photo.get("artifacts", _UNSET))
    photo["artifacts"] = {}
    photo["state"] = "approved"
    return remembered


def _restore_forced(data, stem, remembered):
    state, artifacts = remembered
    photo = data["photos"][stem]
    photo["state"] = state
    if artifacts is _UNSET:
        photo.pop("artifacts", None)
    else:
        photo["artifacts"] = artifacts


def process_all(stems: set[str] | None = None, force: bool = False,
                collect: dict | None = None):
    if collect is not None:
        for key in ("published", "advanced", "failed"):
            collect.setdefault(key, [])
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

        for stem in _selected_stems(data, stems, collect):
            remembered = None
            persisted = False
            try:
                fingerprint = _current_fingerprint(stem)
                state = manifest.effective_state(data, stem, fingerprint)
                if state != data["photos"][stem]["state"]:
                    manifest.set_state(data, stem, state)
                    manifest.save(data)

                if force and state in ("rendered", "verified"):
                    remembered = _force_downgrade(data, stem)
                    state = "approved"

                if state == "ingested":
                    _stage_event(stem, "preview")
                    render.ensure_sidecar_all(stem)
                    for index, style in enumerate(paths.STYLES, start=1):
                        preview_photo(stem, style)
                        jsonio.emit({"event": "progress", "stem": stem,
                                     "stage": "preview", "index": index,
                                     "total": len(paths.STYLES),
                                     "detail": style})
                    manifest.set_state(data, stem, "preview_ready")
                    manifest.save(data)
                    print(f"{stem}: previews ready — visual review required")
                    if collect is not None:
                        collect["advanced"].append(
                            {"stem": stem, "state": "preview_ready"})
                elif state in ("preview_ready", "review_required"):
                    print(f"{stem}: awaiting visual review + approve")
                elif state == "approved":
                    stored = data["photos"][stem].get("artifacts", {})
                    if not stored:
                        _stage_event(stem, "render")
                        render_photo(stem)
                    else:
                        current = current_artifact_deps(stem)
                        stale = set(manifest.stale_artifacts(
                            data, stem, current
                        ))
                        if stale == set(current):
                            _stage_event(stem, "render")
                            render_photo(stem)
                        elif stale:
                            _stage_event(stem, "render")
                            render_photo(stem, only=stale)
                    persisted = _finish_verified(data, stem, collect)
                elif state == "rendered":
                    persisted = _finish_verified(data, stem, collect)
                elif state == "verified":
                    current = current_artifact_deps(stem)
                    stale = set(manifest.stale_artifacts(
                        data, stem, current
                    ))
                    if stale:
                        _stage_event(stem, "render")
                        render_photo(stem, only=stale)
                        persisted = _finish_verified(data, stem, collect)
            # Broad by design: the render and publish paths also raise
            # ValueError, OSError, CalledProcessError, CropError and PdfError,
            # and in collect mode any of them escaping would abort the batch
            # and discard the partial result the aggregate envelope exists to
            # report. BaseException (KeyboardInterrupt, SystemExit) still
            # propagates.
            except Exception as error:  # noqa: BLE001
                if isinstance(error, RuntimeError) and (
                        str(error) == MANUAL_ASSETS_ERROR):
                    print(f"{stem}: skipped — {error}")
                elif collect is None:
                    # Legacy runs still hard-stop on the first real failure;
                    # per-stem isolation exists only for the aggregate result.
                    raise
                else:
                    collect["failed"].append(
                        {"stem": stem,
                         # A CommandError already carries a contract code;
                         # anything else is reported as a render failure.
                         "code": getattr(error, "code", "RENDER_FAILED"),
                         "message": str(error)})
            finally:
                if remembered is not None and not persisted:
                    _restore_forced(data, stem, remembered)


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
    metadata.strip(output, lab["keep_capture_date"], ppi=lab["ppi"])
    return output
