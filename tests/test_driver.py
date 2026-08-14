import hashlib
from pathlib import Path

import pytest

from pipeline import (crops, driver, geometry, jsonio, manifest, metadata,
                      paths, pdfs, publish, recipe, render, subject, toolchain)


@pytest.fixture(autouse=True)
def _no_real_toolchain(monkeypatch):
    monkeypatch.setattr(toolchain, "verify", lambda path: [])


def test_run_blocks_unapproved(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "preview_ready")
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    calls = []
    monkeypatch.setattr(driver, "render_photo", lambda stem: calls.append(stem))

    driver.process_all()

    assert calls == []


def test_approved_photo_flows_to_verified(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(
        driver,
        "render_photo",
        lambda stem: tmp_repo / "staging" / f"{stem}.tmp",
    )
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: None)

    driver.process_all()

    assert manifest.load()["photos"]["P1"]["state"] == "verified"


def test_fingerprint_change_demotes(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "old"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "new")
    monkeypatch.setattr(
        driver,
        "render_photo",
        lambda stem: (_ for _ in ()).throw(AssertionError),
    )

    driver.process_all()

    assert manifest.load()["photos"]["P1"]["state"] == "review_required"


def test_verify_tool_drift_demotes_to_rendered(tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "verified")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(
        toolchain,
        "verify",
        lambda path: [{"name": "qpdf", "problem": "hash mismatch"}],
    )
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: None)
    monkeypatch.setattr(
        driver,
        "render_photo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
    )

    driver.process_all()

    assert manifest.load()["photos"]["P1"]["state"] == "verified"


def test_render_tool_drift_hard_stops(tmp_repo, monkeypatch):
    monkeypatch.setattr(
        toolchain,
        "verify",
        lambda path: [{"name": "rawtherapee", "problem": "hash mismatch"}],
    )

    with pytest.raises(RuntimeError):
        driver.process_all()


def test_approve_requires_expression_audit(tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    recipe.save("P1", rec)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    with pytest.raises(RuntimeError):
        driver.approve("P1")


def test_approve_persists_subject_crops_before_fingerprinting(
        tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    rec["expression_audit"] = ["all expressions reviewed"]
    recipe.save("P1", rec)
    preview = tmp_repo / "previews/P1_natural_preview.jpg"
    preview.write_bytes(b"preview")
    bbox = {"x": 0.05, "y": 0.3, "w": 0.2, "h": 0.25}
    detected = []

    def group_bbox(image_path):
        detected.append(image_path)
        return bbox

    monkeypatch.setattr(subject, "group_bbox", group_bbox)
    expected = {
        crop: geometry.subject_crop_norm(5784, 4344, crop, True, bbox)
        for crop in paths.CROPS
    }
    seen = []

    def fingerprint(stem):
        saved = recipe.load(stem)
        seen.append(saved["crops"])
        return "fp-bound-to-persisted-crops"

    monkeypatch.setattr(driver, "_current_fingerprint", fingerprint)

    driver.approve("P1")

    saved = recipe.load("P1")
    assert detected == [preview]
    assert seen == [expected]
    assert saved["crops"] == expected
    assert saved["approval"]["fingerprint"] == "fp-bound-to-persisted-crops"


def test_approve_centers_default_crops_when_subject_detection_returns_none(
        tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    rec["expression_audit"] = ["all expressions reviewed"]
    recipe.save("P1", rec)
    preview = tmp_repo / "previews/P1_natural_preview.jpg"
    preview.write_bytes(b"preview")
    detected = []
    monkeypatch.setattr(
        subject,
        "group_bbox",
        lambda image_path: detected.append(image_path),
    )
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    driver.approve("P1")

    expected = {
        crop: geometry.centered_crop_norm(5784, 4344, crop, True)
        for crop in paths.CROPS
    }
    assert detected == [preview]
    assert recipe.load("P1")["crops"] == expected


def test_approve_notes_missing_natural_preview_and_uses_centered_crops(
        tmp_repo, monkeypatch, capsys):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    rec["expression_audit"] = ["all expressions reviewed"]
    recipe.save("P1", rec)
    monkeypatch.setattr(
        subject,
        "group_bbox",
        lambda image_path: (_ for _ in ()).throw(AssertionError),
    )
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    driver.approve("P1")

    expected = {
        crop: geometry.centered_crop_norm(5784, 4344, crop, True)
        for crop in paths.CROPS
    }
    assert recipe.load("P1")["crops"] == expected
    assert capsys.readouterr().out == (
        "NOTE: P1: natural preview missing; using geometric center\n"
    )


def test_approve_warns_when_group_is_larger_than_crop_window(
        tmp_repo, monkeypatch, capsys):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    rec["expression_audit"] = ["all expressions reviewed"]
    recipe.save("P1", rec)
    preview = tmp_repo / "previews/P1_natural_preview.jpg"
    preview.write_bytes(b"preview")
    monkeypatch.setattr(
        subject,
        "group_bbox",
        lambda image_path: {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
    )
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    driver.approve("P1")

    assert capsys.readouterr().out == (
        "WARNING: P1 8x10: group extends beyond crop window — "
        "review before approving\n"
        "WARNING: P1 5x7: group extends beyond crop window — "
        "review before approving\n"
    )


def test_approve_requires_render_dims_for_default_crops(tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec["expression_audit"] = ["all expressions reviewed"]
    recipe.save("P1", rec)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    with pytest.raises(RuntimeError, match="croppreview/preview"):
        driver.approve("P1")

    assert recipe.load("P1")["crops"] == {"8x10": None, "5x7": None}


def test_render_photo_records_dims_and_strips_before_pdfs(tmp_repo, monkeypatch):
    raw = tmp_repo / "archive/P1.RW2"
    raw.write_bytes(b"raw")
    rec = recipe.new(
        "P1", hashlib.sha256(b"raw").hexdigest(), 5776, 4336
    )
    rec["overrides"]["denoise"] = True
    recipe.save("P1", rec)
    lab = {"jpeg_quality": 92, "ppi": 300, "keep_capture_date": True}
    monkeypatch.setattr(driver, "_lab", lambda: lab)
    monkeypatch.setattr(driver, "_dims", lambda path: (5784, 4344))
    denoise = tmp_repo / "run/denoise.pp3"
    monkeypatch.setattr(render, "denoise_profile", lambda: denoise)
    render_calls = []

    def fake_render(raw_path, style, output, fmt, quality, extra_profiles=()):
        render_calls.append((raw_path, style, tuple(extra_profiles)))
        Path(output).write_bytes(b"tif")

    monkeypatch.setattr(render, "rt_render", fake_render)

    def fake_jpg(tif, output, window, target, sharpen, quality, ppi):
        Path(output).write_bytes(b"jpg")

    monkeypatch.setattr(crops, "jpg_from_tif", fake_jpg)
    stripped = []
    monkeypatch.setattr(
        metadata,
        "strip",
        lambda path, keep, ppi=None: stripped.append((Path(path).name, ppi)),
    )

    raster_names = {
        name
        for name in manifest.artifact_names("P1")
        if name.endswith((".tif", ".jpg"))
    }

    def fake_wrap(jpg, output, page_inches):
        assert {name for name, _ in stripped} == raster_names
        Path(output).write_bytes(b"pdf")

    monkeypatch.setattr(pdfs, "wrap", fake_wrap)

    def fake_comparison(stem, native_jpgs, staging):
        assert {name for name, _ in stripped} == raster_names
        assert set(native_jpgs) == set(paths.STYLES)
        output = Path(staging) / f"{stem}_comparison.pdf"
        source = Path(staging) / f"{stem}_comparison_src.jpg"
        output.write_bytes(b"pdf")
        source.write_bytes(b"jpg")
        return output, source

    monkeypatch.setattr(pdfs, "comparison_sheet", fake_comparison)

    staging = driver.render_photo("P1")

    assert render_calls == [
        (raw, style, (denoise,)) for style in paths.STYLES
    ]
    assert {
        name: ppi for name, ppi in stripped
    } == {
        name: 300 if name.endswith(".jpg") else None for name in raster_names
    }
    saved = recipe.load("P1")
    assert (saved["render_width"], saved["render_height"]) == (5784, 4344)
    assert {path.name for path in staging.iterdir()} == (
        set(manifest.artifact_names("P1")) | {"P1_comparison_src.jpg"}
    )


def test_render_photo_refuses_archive_hash_mismatch(tmp_repo, monkeypatch):
    (tmp_repo / "archive/P1.RW2").write_bytes(b"changed")
    recipe.save("P1", recipe.new("P1", "expected", 5776, 4336))
    monkeypatch.setattr(
        render,
        "rt_render",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError),
    )

    with pytest.raises(RuntimeError, match="hash"):
        driver.render_photo("P1")


def test_render_photo_refuses_manual_assets_before_rendering(
        tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec["manual_assets"] = [{"file": "P1_retouch.tif", "sha256": "abc"}]
    recipe.save("P1", rec)
    monkeypatch.setattr(
        render,
        "resolve_raw",
        lambda stem: (_ for _ in ()).throw(AssertionError("must not resolve")),
    )

    with pytest.raises(
            RuntimeError, match="^manual assets present; outside automated re-render$"):
        driver.render_photo("P1")


def test_current_artifact_deps_covers_allowlist(tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    recipe.save("P1", rec)
    monkeypatch.setattr(
        render,
        "style_hashes",
        lambda stem: {style: style for style in paths.STYLES},
    )
    monkeypatch.setattr(render, "seed_hash", lambda: "seed")
    monkeypatch.setattr(driver, "_lock", lambda: {})
    monkeypatch.setattr(
        driver,
        "_lab",
        lambda: {
            "submission_format": "jpeg",
            "jpeg_quality": 92,
            "embed_icc": True,
            "max_file_bytes": 1,
            "filename_rules": "x",
            "strip_metadata_beyond_allowlist": True,
            "keep_capture_date": True,
            "ppi": 300,
        },
    )

    deps = driver.current_artifact_deps("P1")

    assert set(deps) == set(manifest.artifact_names("P1"))
    expected = geometry.centered_crop_norm(5784, 4344, "8x10", True)
    assert deps["P1_natural_8x10.jpg"]["crop"] == expected


def test_process_all_passes_only_stale_artifacts(tmp_repo, monkeypatch):
    names = manifest.artifact_names("P1")
    current = {name: {"version": 1} for name in names}
    stored = dict(current)
    stored["P1_natural_8x10.jpg"] = {"version": 0}
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"].update(fingerprint="fp", artifacts=stored)
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "current_artifact_deps", lambda stem: current)
    calls = []
    monkeypatch.setattr(
        driver,
        "render_photo",
        lambda stem, only=None: calls.append((stem, only)),
    )
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: current)

    driver.process_all()

    assert calls == [("P1", {"P1_natural_8x10.jpg"})]
    photo = manifest.load()["photos"]["P1"]
    assert photo["state"] == "verified"
    assert photo["artifacts"] == current


def test_process_all_refreshes_stale_artifacts_for_verified_photo(
        tmp_repo, monkeypatch):
    names = manifest.artifact_names("P1")
    current = {name: {"version": 2} for name in names}
    stored = dict(current)
    stale_name = "P1_bw_5x7.jpg"
    stored[stale_name] = {"version": 1}
    m = manifest.load()
    manifest.set_state(m, "P1", "verified")
    m["photos"]["P1"].update(fingerprint="fp", artifacts=stored)
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "current_artifact_deps", lambda stem: current)
    calls = []
    monkeypatch.setattr(
        driver,
        "render_photo",
        lambda stem, only=None: calls.append((stem, only)),
    )
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: current)

    driver.process_all()

    assert calls == [("P1", {stale_name})]
    photo = manifest.load()["photos"]["P1"]
    assert photo["state"] == "verified"
    assert photo["artifacts"] == current


def test_process_all_renders_approved_photo_without_stored_artifacts(
        tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    calls = []
    monkeypatch.setattr(
        driver,
        "render_photo",
        lambda stem: calls.append(stem),
    )
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})

    driver.process_all()

    assert calls == ["P1"]


def test_process_all_skips_manual_assets_and_continues(
        tmp_repo, monkeypatch, capsys):
    m = manifest.load()
    for stem in ("P1", "P2"):
        manifest.set_state(m, stem, "approved")
        m["photos"][stem]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    calls = []

    def render_one(stem):
        calls.append(stem)
        if stem == "P1":
            raise RuntimeError(
                "manual assets present; outside automated re-render")

    monkeypatch.setattr(driver, "render_photo", render_one)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})

    driver.process_all()

    assert calls == ["P1", "P2"]
    assert manifest.load()["photos"]["P1"]["state"] == "approved"
    assert manifest.load()["photos"]["P2"]["state"] == "verified"
    output = capsys.readouterr().out
    assert "P1" in output
    assert "manual assets present; outside automated re-render" in output


def test_publish_uses_exact_allowlist_and_provenance(tmp_repo, monkeypatch):
    recipe.save("P1", recipe.new("P1", "raw-hash", 5776, 4336))
    deps = {name: {"dep": name} for name in manifest.artifact_names("P1")}
    lock = {"rawtherapee": {"sha256": "x"}}
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "_lock", lambda: lock)
    monkeypatch.setattr(driver, "current_artifact_deps", lambda stem: deps)
    calls = []
    monkeypatch.setattr(
        publish,
        "publish",
        lambda *args: calls.append(args) or (tmp_repo / "Output/photos/P1/v001"),
    )
    monkeypatch.setattr(publish, "rebuild_views", lambda: None)

    result = driver._publish_photo("P1")

    assert result == deps
    stem, staging, provenance, allowlist = calls[0]
    assert stem == "P1"
    assert staging == tmp_repo / "staging/P1.tmp"
    assert allowlist == set(manifest.artifact_names("P1"))
    assert provenance == {
        "fingerprint": "fp",
        "raw_sha256": "raw-hash",
        "toolchain": lock,
        "artifacts": deps,
    }


def test_crop_preview_uses_recipe_window_and_lab_ppi(tmp_repo, monkeypatch):
    rec = recipe.new("P1", "raw", 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    rec["crops"]["8x10"] = {"x": 0.1, "y": 0.0, "w": 0.8, "h": 1.0}
    recipe.save("P1", rec)
    tif = tmp_repo / "staging/P1.tmp/P1_natural.tif"
    tif.parent.mkdir()
    tif.write_bytes(b"tif")
    monkeypatch.setattr(
        driver,
        "_lab",
        lambda: {"jpeg_quality": 92, "ppi": 300, "keep_capture_date": True},
    )
    validations = []
    monkeypatch.setattr(
        geometry,
        "validate_crop",
        lambda *args: validations.append(args),
    )

    def fake_jpg(tif_path, output, window, target, sharpen, quality, ppi):
        Path(output).write_bytes(b"preview")

    monkeypatch.setattr(crops, "jpg_from_tif", fake_jpg)
    strip_calls = []
    monkeypatch.setattr(
        metadata,
        "strip",
        lambda path, keep, ppi=None: strip_calls.append((path, keep, ppi)),
    )

    output = driver.crop_preview("P1", "natural", "8x10")

    assert output == tmp_repo / "previews/P1_natural_8x10_croppreview.jpg"
    assert validations == [
        (rec["crops"]["8x10"], 5784, 4344, "8x10", True, 300)
    ]
    assert strip_calls == [(output, True, 300)]
    assert output.read_bytes() == b"preview"


def _seed_preview_repo(tmp_repo, monkeypatch):
    """Styles + lock + lab profile + a REAL raw file whose hash matches the
    recipe (preview_photo verifies it — a fabricated hash fails)."""
    import hashlib as _hl
    import json as _json
    import pathlib, shutil as _sh
    from pipeline import recipe, toolchain
    from pipeline.paths import STYLES
    for s in STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    raw = tmp_repo / "Input/P1.RW2"
    raw.write_bytes(b"raw-bytes")
    recipe.save("P1", recipe.new(
        "P1", _hl.sha256(b"raw-bytes").hexdigest(), 5776, 4336))
    return raw


def test_preview_photo_atomic_and_records(tmp_repo, monkeypatch):
    from pipeline import driver, paths, provenance, recipe, render
    _seed_preview_repo(tmp_repo, monkeypatch)

    def fake_rt(raw, style, out, fmt, quality, extra_profiles=()):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"JPG:" + style.encode())
    monkeypatch.setattr(render, "rt_render", fake_rt)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))

    out = driver.preview_photo("P1", "natural")
    assert out == paths.previews_dir() / "P1_natural_preview.jpg"
    assert out.read_bytes() == b"JPG:natural"
    rec = recipe.load("P1")
    assert rec["render_width"] == 5784
    assert rec["previews"]["natural"]["content"] == provenance.content_hash(out)


def test_preview_photo_refuses_raw_hash_mismatch(tmp_repo, monkeypatch):
    from pipeline import driver, render
    raw = _seed_preview_repo(tmp_repo, monkeypatch)
    raw.write_bytes(b"DIFFERENT raw bytes")
    monkeypatch.setattr(render, "rt_render",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not render")))
    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="hash mismatch"):
        driver.preview_photo("P1", "natural")


def test_preview_photo_failure_keeps_previous_jpg(tmp_repo, monkeypatch):
    from pipeline import driver, paths, render
    _seed_preview_repo(tmp_repo, monkeypatch)
    prior = paths.previews_dir() / "P1_natural_preview.jpg"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_bytes(b"OLD")

    def boom(raw, style, out, fmt, quality, extra_profiles=()):
        raise render.RenderError("rt exploded")
    monkeypatch.setattr(render, "rt_render", boom)

    import pytest as _pytest
    with _pytest.raises(render.RenderError):
        driver.preview_photo("P1", "natural")
    assert prior.read_bytes() == b"OLD"


def test_preview_photo_detects_mid_render_input_edit(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, render
    _seed_preview_repo(tmp_repo, monkeypatch)
    before = (tmp_repo / "recipes/P1.yaml").read_bytes()

    def rt_that_edits_inputs(raw, style, out, fmt, quality, extra_profiles=()):
        (paths.sidecars_dir() / "P1_natural.pp3").write_text(
            "[Exposure]\nCompensation=0.5\n")     # edit lands mid-render
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"JPG")
    monkeypatch.setattr(render, "rt_render", rt_that_edits_inputs)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))

    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="inputs changed"):
        driver.preview_photo("P1", "natural")
    assert (tmp_repo / "recipes/P1.yaml").read_bytes() == before
    assert not (paths.previews_dir() / "P1_natural_preview.jpg").exists()


def test_preview_photo_passes_denoise_profile_when_overridden(
        tmp_repo, monkeypatch):
    from pipeline import driver, recipe, render
    _seed_preview_repo(tmp_repo, monkeypatch)
    rec = recipe.load("P1")
    rec["overrides"]["denoise"] = True
    recipe.save("P1", rec)
    calls = []

    def fake_rt(raw, style, out, fmt, quality, extra_profiles=()):
        calls.append(extra_profiles)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"JPG")
    monkeypatch.setattr(render, "rt_render", fake_rt)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))

    driver.preview_photo("P1", "natural")

    assert calls == [(render.denoise_profile(),)]


def test_preview_photo_dims_failure_leaves_preview_and_recipe(
        tmp_repo, monkeypatch):
    from pipeline import driver, paths, render
    _seed_preview_repo(tmp_repo, monkeypatch)
    prior = paths.previews_dir() / "P1_natural_preview.jpg"
    prior.parent.mkdir(parents=True, exist_ok=True)
    prior.write_bytes(b"OLD")
    before = (tmp_repo / "recipes/P1.yaml").read_bytes()

    def fake_rt(raw, style, out, fmt, quality, extra_profiles=()):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"JPG")
    monkeypatch.setattr(render, "rt_render", fake_rt)
    monkeypatch.setattr(driver, "_dims", lambda p: (_ for _ in ()).throw(
        RuntimeError(f"could not identify dimensions for {p}: boom")))

    import pytest as _pytest
    with _pytest.raises(RuntimeError, match="could not identify dimensions"):
        driver.preview_photo("P1", "natural")
    assert prior.read_bytes() == b"OLD"
    assert (tmp_repo / "recipes/P1.yaml").read_bytes() == before


def test_crop_windows_suggests_with_basis(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, subject
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    rec = recipe.load("P1")
    rec["render_width"], rec["render_height"] = 5784, 4344
    recipe.save("P1", rec)
    preview = paths.previews_dir() / "P1_natural_preview.jpg"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"x")
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda p: ({"x": 0.4, "y": 0.3, "w": 0.2, "h": 0.3},
                                   "faces"))
    recipe_bytes = (tmp_repo / "recipes/P1.yaml").read_bytes()
    state = _recipe_state(tmp_repo)
    result = driver.crop_windows("P1")
    assert result["basis"] == "faces"
    assert set(result["windows"]) == set(paths.CROPS)
    assert all(w["source"] == "suggested" for w in result["windows"].values())
    before = recipe.load("P1")
    assert before["crops"] == {"8x10": None, "5x7": None}   # nothing persisted
    # Byte-identical, not merely equal once parsed — and unwritten, not merely
    # unchanged: a re-save with the same content is still a write this command
    # must never make.
    assert (tmp_repo / "recipes/P1.yaml").read_bytes() == recipe_bytes
    assert _recipe_state(tmp_repo) == state


def test_crop_windows_detector_error_falls_back_centered(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, subject
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    rec = recipe.load("P1")
    rec["render_width"], rec["render_height"] = 5784, 4344
    recipe.save("P1", rec)
    p = paths.previews_dir() / "P1_natural_preview.jpg"
    p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda path: (None, "detector_error"))
    result = driver.crop_windows("P1")
    assert result["basis"] == "detector_error"


def test_crop_windows_requires_dims(tmp_repo):
    from pipeline import driver, jsonio, recipe
    import pytest as _pytest
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    with _pytest.raises(jsonio.CommandError) as e:
        driver.crop_windows("P1")
    assert e.value.code == "BAD_INPUT"


def _recipe_state(tmp_repo, stem="P1"):
    """Bytes plus identity: recipe.save() emits deterministic YAML, so a
    content-identical re-save is invisible to a bytes comparison alone, while
    its temp-file + os.replace always lands a new inode."""
    path = tmp_repo / f"recipes/{stem}.yaml"
    return path.read_bytes(), path.stat().st_ino


def _crop_windows_repo(dims=(5784, 4344), crops=None):
    from pipeline import recipe
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    rec = recipe.load("P1")
    rec["render_width"], rec["render_height"] = dims
    if crops:
        rec["crops"].update(crops)
    recipe.save("P1", rec)
    return rec


def test_crop_windows_all_persisted_reports_no_basis(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, subject
    window = {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.6}
    _crop_windows_repo(crops={crop: dict(window) for crop in paths.CROPS})
    # Fully persisted means no suggestion runs at all — not even the detector.
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda p: (_ for _ in ()).throw(
                            AssertionError("detector must not run")))
    recipe_bytes = (tmp_repo / "recipes/P1.yaml").read_bytes()
    state = _recipe_state(tmp_repo)

    result = driver.crop_windows("P1")

    assert result["basis"] is None
    assert result["windows"] == {
        crop: dict(window, source="persisted") for crop in paths.CROPS}
    assert recipe.load("P1")["crops"] == {
        crop: window for crop in paths.CROPS}
    assert (tmp_repo / "recipes/P1.yaml").read_bytes() == recipe_bytes
    assert _recipe_state(tmp_repo) == state


def test_crop_windows_mixes_persisted_and_suggested(tmp_repo, monkeypatch):
    from pipeline import driver, paths, recipe, subject
    window = {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.6}
    _crop_windows_repo(crops={"8x10": dict(window)})
    preview = paths.previews_dir() / "P1_natural_preview.jpg"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"x")
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda p: (None, "no_faces"))
    recipe_bytes = (tmp_repo / "recipes/P1.yaml").read_bytes()
    state = _recipe_state(tmp_repo)

    result = driver.crop_windows("P1")

    assert result["basis"] == "center"
    assert result["windows"]["8x10"] == dict(window, source="persisted")
    assert result["windows"]["5x7"]["source"] == "suggested"
    assert recipe.load("P1")["crops"] == {"8x10": window, "5x7": None}
    assert (tmp_repo / "recipes/P1.yaml").read_bytes() == recipe_bytes
    assert _recipe_state(tmp_repo) == state


def test_crop_windows_requires_dims_when_one_window_persisted(tmp_repo):
    from pipeline import driver, jsonio, recipe
    import pytest as _pytest
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    rec = recipe.load("P1")
    rec["crops"]["8x10"] = {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.6}
    recipe.save("P1", rec)
    with _pytest.raises(jsonio.CommandError) as e:
        driver.crop_windows("P1")
    assert e.value.code == "BAD_INPUT"


def test_crop_windows_without_preview_is_centered(tmp_repo, monkeypatch):
    from pipeline import driver, geometry, paths, subject
    _crop_windows_repo()
    monkeypatch.setattr(subject, "group_bbox_detail",
                        lambda p: (_ for _ in ()).throw(
                            AssertionError("detector must not run")))

    result = driver.crop_windows("P1")

    assert result["basis"] == "center"
    for crop in paths.CROPS:
        expected = geometry.centered_crop_norm(5784, 4344, crop, True)
        assert result["windows"][crop] == dict(expected, source="suggested")


def _seed_approvable(tmp_repo, monkeypatch):
    import json as _json
    from pipeline import paths, recipe, toolchain
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    # labprofile.load validates the exact field set — always copy the real
    # profile; hand-written minimal YAML fails its schema check.
    monkeypatch.setattr(toolchain, "entries_for", lambda lock, names: {})
    rec = recipe.new("P1", "aa" * 32, 5776, 4336)
    rec["render_width"], rec["render_height"] = 5784, 4344
    recipe.save("P1", rec)
    # Valid geometry for a landscape 5784x4344 render at 300 PPI, deliberately
    # offset from centered_crop_norm so the tests can tell a persisted
    # submission apart from a recomputed default.
    return {
        "expression_audit": ["eyes open — all: pass"],
        "crops": {
            "8x10": {"x": 0.05, "y": 0.0, "w": 0.9388, "h": 1.0},
            "5x7": {"x": 0.0, "y": 0.04, "w": 1.0, "h": 0.951},
        },
    }


def test_approve_review_happy_path(tmp_repo, monkeypatch):
    from pipeline import driver, manifest, recipe
    review = _seed_approvable(tmp_repo, monkeypatch)
    result = driver.approve_review("P1", review)
    assert result["state"] == "approved"
    rec = recipe.load("P1")
    assert rec["approval"]["fingerprint"] == result["fingerprint"]
    assert rec["crops"] == review["crops"]
    assert rec["expression_audit"] == ["eyes open — all: pass"]
    m = manifest.load_readonly()
    assert m["photos"]["P1"]["state"] == "approved"
    assert m["photos"]["P1"]["fingerprint"] == result["fingerprint"]


def test_approve_review_stale_revision_changes_nothing(tmp_repo, monkeypatch):
    from pipeline import driver, jsonio, recipe
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["expected_review_revision"] = "sha256:not-the-current-one"
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "STALE_REVIEW"
    assert recipe.load("P1")["approval"]["fingerprint"] is None


def test_approve_review_requires_both_crops_and_audit(tmp_repo, monkeypatch):
    from pipeline import driver, jsonio
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    del review["crops"]["5x7"]
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["expression_audit"] = []
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"
    # Shapes that would otherwise blow up as AttributeError → INTERNAL.
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["crops"] = [{"x": 0.05, "y": 0.0, "w": 0.9388, "h": 1.0}]
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["crops"]["8x10"] = [0.05, 0.0, 0.9388, 1.0]
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["expression_audit"] = "eyes open — all: pass"
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "BAD_INPUT"


def test_approve_review_with_matching_revision_requires_fresh_previews(
        tmp_repo, monkeypatch):
    from pipeline import driver, jsonio, provenance, recipe
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    rec = recipe.load("P1")
    review["expected_review_revision"] = provenance.review_revision("P1", rec)
    # No previews rendered → every style is stale → STALE_REVIEW
    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)
    assert e.value.code == "STALE_REVIEW"


def test_approve_review_strips_echoed_source_tag(tmp_repo, monkeypatch):
    from pipeline import driver, recipe
    review = _seed_approvable(tmp_repo, monkeypatch)
    geometry_only = {c: dict(w) for c, w in review["crops"].items()}
    for window in review["crops"].values():
        window["source"] = "suggested"

    driver.approve_review("P1", review)

    # The recipe stores geometry alone; a stray tag would later fail
    # recipe.fingerprint's numeric check on a recipe already on disk.
    assert recipe.load("P1")["crops"] == geometry_only


def test_approve_review_rejects_invalid_window_without_persisting(
        tmp_repo, monkeypatch):
    from pipeline import driver, jsonio, recipe
    import pytest as _pytest
    review = _seed_approvable(tmp_repo, monkeypatch)
    review["crops"]["5x7"]["h"] = 0.5  # aspect no longer matches 5x7

    with _pytest.raises(jsonio.CommandError) as e:
        driver.approve_review("P1", review)

    assert e.value.code == "BAD_INPUT"
    rec = recipe.load("P1")
    assert rec["crops"] == {"8x10": None, "5x7": None}
    assert rec["approval"]["fingerprint"] is None
    assert rec["expression_audit"] == []


def test_process_all_stem_scoping(tmp_repo, monkeypatch):
    from pipeline import driver, manifest
    m = manifest.load()
    for stem in ("P1", "P2"):
        manifest.set_state(m, stem, "approved")
        m["photos"][stem]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    rendered = []
    monkeypatch.setattr(driver, "render_photo",
                        lambda stem, only=None: rendered.append(stem))
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    driver.process_all(stems={"P2"})
    assert rendered == ["P2"]


def test_process_all_force_rerenders_verified(tmp_repo, monkeypatch):
    from pipeline import driver, manifest
    m = manifest.load()
    manifest.set_state(m, "P1", "verified")
    m["photos"]["P1"]["fingerprint"] = "fp"
    m["photos"]["P1"]["artifacts"] = {"P1_natural.tif": {"x": 1}}
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    rendered = []
    monkeypatch.setattr(driver, "render_photo",
                        lambda stem, only=None: rendered.append((stem, only)))
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    driver.process_all(stems={"P1"}, force=True)
    assert rendered == [("P1", None)]            # full re-render, not stale-only


def test_process_all_collect_shapes(tmp_repo, monkeypatch):
    from pipeline import driver, manifest
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: ["bad pixels"])
    collect = {}
    driver.process_all(stems={"P1"}, collect=collect)
    assert collect["failed"][0]["stem"] == "P1"
    assert collect["failed"][0]["code"] == "VERIFY_FAILED"


def test_render_photo_emits_progress_in_json_mode(tmp_repo, monkeypatch):
    import json as _json
    from pipeline import crops, driver, jsonio, metadata, paths, pdfs, recipe, render
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    raw = tmp_repo / "Input/P1.RW2"
    raw.write_bytes(b"rawbytes")
    import hashlib as _hl
    rec = recipe.new("P1", _hl.sha256(b"rawbytes").hexdigest(), 5776, 4336)
    recipe.save("P1", rec)

    def fake_rt(raw_path, style, out, fmt, quality, extra_profiles=()):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"TIF")
    monkeypatch.setattr(render, "rt_render", fake_rt)
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))
    monkeypatch.setattr(crops, "jpg_from_tif",
                        lambda tif, out, win, tgt, sh, q, ppi:
                        out.write_bytes(b"JPG"))
    monkeypatch.setattr(pdfs, "wrap",
                        lambda jpg, out, inches: out.write_bytes(b"PDF"))
    monkeypatch.setattr(pdfs, "comparison_sheet",
                        lambda stem, jpgs, staging:
                        (staging / f"{stem}_comparison.pdf").write_bytes(b"PDF"))
    monkeypatch.setattr(metadata, "strip",
                        lambda p, keep, ppi=None: None)

    events = []
    monkeypatch.setattr(jsonio, "emit", lambda e: events.append(e))
    driver.render_photo("P1")

    render_events = [e for e in events
                     if e.get("event") == "progress" and e["stage"] == "render"]
    assert render_events, "no render progress events emitted"
    assert render_events[0]["index"] == 1                 # 1-based
    assert all(e["stem"] == "P1" for e in render_events)
    assert all(e["total"] == render_events[0]["total"] for e in render_events)
    assert len(render_events) == render_events[0]["total"]


def test_render_photo_progress_names_every_requested_artifact(
        tmp_repo, monkeypatch):
    """One event per requested artifact, indexes 1..total, no duplicates."""
    import json as _json
    from pipeline import crops, driver, jsonio, metadata, paths, pdfs, recipe, render
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    (tmp_repo / "Input/P1.RW2").write_bytes(b"rawbytes")
    recipe.save("P1", recipe.new(
        "P1", hashlib.sha256(b"rawbytes").hexdigest(), 5776, 4336))

    monkeypatch.setattr(render, "rt_render",
                        lambda raw, style, out, fmt, quality,
                        extra_profiles=(): (out.parent.mkdir(
                            parents=True, exist_ok=True),
                            out.write_bytes(b"TIF")))
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))
    monkeypatch.setattr(crops, "jpg_from_tif",
                        lambda tif, out, win, tgt, sh, q, ppi:
                        out.write_bytes(b"JPG"))
    monkeypatch.setattr(pdfs, "wrap",
                        lambda jpg, out, inches: out.write_bytes(b"PDF"))
    monkeypatch.setattr(pdfs, "comparison_sheet",
                        lambda stem, jpgs, staging:
                        (staging / f"{stem}_comparison.pdf").write_bytes(b"PDF"))
    monkeypatch.setattr(metadata, "strip", lambda p, keep, ppi=None: None)

    events = []
    monkeypatch.setattr(jsonio, "emit", lambda e: events.append(e))
    driver.render_photo("P1")

    progress = [e for e in events if e.get("event") == "progress"]
    names = [e["detail"] for e in progress]
    assert sorted(names) == sorted(manifest.artifact_names("P1"))
    assert [e["index"] for e in progress] == list(range(1, len(names) + 1))
    assert all(e["total"] == len(names) for e in progress)


def test_render_photo_progress_counts_only_requested_artifacts(
        tmp_repo, monkeypatch):
    """`only=` renders a whole style TIF but must not count unrequested names."""
    import json as _json
    from pipeline import crops, driver, jsonio, metadata, paths, pdfs, recipe, render
    for s in paths.STYLES:
        (tmp_repo / "config/styles" / f"{s}.pp3").write_text(f"# {s}\n")
    (tmp_repo / "config/toolchain.lock").write_text(_json.dumps({}))
    import pathlib, shutil as _sh
    _REPO = pathlib.Path(__file__).resolve().parent.parent
    _sh.copy2(_REPO / "config/lab-profiles/generic-v1.yaml",
              tmp_repo / "config/lab-profiles/generic-v1.yaml")
    (tmp_repo / "Input/P1.RW2").write_bytes(b"rawbytes")
    rec = recipe.new("P1", hashlib.sha256(b"rawbytes").hexdigest(), 5776, 4336)
    rec.update(render_width=5784, render_height=4344)
    recipe.save("P1", rec)

    monkeypatch.setattr(render, "rt_render",
                        lambda raw, style, out, fmt, quality,
                        extra_profiles=(): (out.parent.mkdir(
                            parents=True, exist_ok=True),
                            out.write_bytes(b"TIF")))
    monkeypatch.setattr(driver, "_dims", lambda p: (5784, 4344))
    monkeypatch.setattr(crops, "jpg_from_tif",
                        lambda tif, out, win, tgt, sh, q, ppi:
                        out.write_bytes(b"JPG"))
    monkeypatch.setattr(metadata, "strip", lambda p, keep, ppi=None: None)

    events = []
    monkeypatch.setattr(jsonio, "emit", lambda e: events.append(e))
    driver.render_photo("P1", only={"P1_natural.jpg"})

    progress = [e for e in events if e.get("event") == "progress"]
    assert [(e["index"], e["total"], e["detail"]) for e in progress] == [
        (1, 1, "P1_natural.jpg")]


def test_process_all_no_args_matches_legacy_flow(tmp_repo, monkeypatch):
    # Same scenario as test_approved_photo_flows_to_verified but through the
    # new signature with no arguments — states and calls must be identical.
    from pipeline import driver, manifest
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    driver.process_all()
    assert manifest.load()["photos"]["P1"]["state"] == "verified"


def test_process_all_without_collect_still_reraises(tmp_repo, monkeypatch):
    """Failure isolation is collect-mode only; legacy runs still hard-stop."""
    m = manifest.load()
    for stem in ("P1", "P2"):
        manifest.set_state(m, stem, "approved")
        m["photos"][stem]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    calls = []

    def render_one(stem, only=None):
        calls.append(stem)
        raise RuntimeError("rawtherapee exploded")

    monkeypatch.setattr(driver, "render_photo", render_one)

    with pytest.raises(RuntimeError, match="rawtherapee exploded"):
        driver.process_all()

    assert calls == ["P1"]


def test_process_all_collect_isolates_failures_and_continues(
        tmp_repo, monkeypatch):
    m = manifest.load()
    for stem in ("P1", "P2", "P3"):
        manifest.set_state(m, stem, "approved")
        m["photos"][stem]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    rendered = []

    def render_one(stem, only=None):
        rendered.append(stem)
        if stem == "P1":
            raise render.RenderError("rawtherapee failed for P1")

    monkeypatch.setattr(driver, "render_photo", render_one)
    monkeypatch.setattr(driver, "verify_photo",
                        lambda stem: ["bad pixels"] if stem == "P2" else [])
    monkeypatch.setattr(driver, "_publish_photo",
                        lambda stem: {"a": {}, "b": {}})
    collect = {}

    driver.process_all(collect=collect)

    assert rendered == ["P1", "P2", "P3"]        # the batch reached every stem
    assert collect["failed"] == [
        {"stem": "P1", "code": "RENDER_FAILED",
         "message": "rawtherapee failed for P1"},
        {"stem": "P2", "code": "VERIFY_FAILED", "message": "bad pixels"},
    ]
    # _publish_photo is stubbed, so no `current` symlink exists to read.
    assert collect["published"] == [
        {"stem": "P3", "version": None, "artifact_count": 2}]
    assert collect["advanced"] == []
    saved = manifest.load()["photos"]
    assert saved["P3"]["state"] == "verified"
    assert saved["P1"]["state"] == "approved"


def test_process_all_collect_clamps_per_stem_codes_to_the_contract(
        tmp_repo, monkeypatch):
    # failed[] is hand-built, so it never passes through
    # CommandError.__init__'s ERROR_CODES check. A contract code carried by a
    # CommandError must survive; anything else — including an exception that
    # happens to expose an out-of-contract .code — must be reported as a
    # render failure, so the set Plan 2 decodes stays closed.
    class Bogus(Exception):
        code = "NOT_A_CONTRACT_CODE"

    class Unhashable(Exception):
        # ERROR_CODES is a frozenset; a membership test on this would raise
        # TypeError inside the handler and abort the batch.
        code = ["not", "a", "string"]

    m = manifest.load()
    for stem in ("P1", "P2", "P3"):
        manifest.set_state(m, stem, "approved")
        m["photos"][stem]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    def render_one(stem, only=None):
        if stem == "P1":
            raise Bogus("exposes a code outside the contract")
        if stem == "P3":
            raise Unhashable("exposes an unhashable code")
        raise jsonio.CommandError("INVALID_STATE", "a real contract code")

    monkeypatch.setattr(driver, "render_photo", render_one)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    collect = {}

    driver.process_all(collect=collect)

    by_stem = {entry["stem"]: entry["code"] for entry in collect["failed"]}
    assert by_stem == {"P1": "RENDER_FAILED", "P2": "INVALID_STATE",
                       "P3": "RENDER_FAILED"}
    assert all(entry["code"] in jsonio.ERROR_CODES
               for entry in collect["failed"])


def test_process_all_collect_keeps_legacy_manual_assets_skip(
        tmp_repo, monkeypatch, capsys):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    def render_one(stem, only=None):
        raise RuntimeError(driver.MANUAL_ASSETS_ERROR)

    monkeypatch.setattr(driver, "render_photo", render_one)
    collect = {}

    driver.process_all(collect=collect)

    assert collect["failed"] == []               # a skip is not a failure
    assert driver.MANUAL_ASSETS_ERROR in capsys.readouterr().out


def test_process_all_unknown_requested_stem_is_not_found(
        tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    collect = {}

    driver.process_all(stems={"P1", "NOPE"}, collect=collect)

    assert [f["stem"] for f in collect["failed"]] == ["NOPE"]
    assert collect["failed"][0]["code"] == "NOT_FOUND"
    assert [p["stem"] for p in collect["published"]] == ["P1"]


def test_process_all_unknown_requested_stem_warns_on_legacy_path(
        tmp_repo, capsys):
    """Without `collect` there is nowhere to record NOT_FOUND, so the typo has
    to reach stdout — otherwise `run --stem TYPO` exits 0 in silence."""
    driver.process_all(stems={"NOPE"})

    captured = capsys.readouterr()
    assert "WARNING: unknown stem NOPE — skipped" in captured.out
    assert captured.err == ""


def test_process_all_force_failure_keeps_published_version(
        tmp_repo, monkeypatch):
    """A forced stem that fails must not have its downgrade persisted — not
    even as a side effect of a later stem's successful manifest.save."""
    m = manifest.load()
    for stem in ("P1", "P2"):
        manifest.set_state(m, stem, "verified")
        m["photos"][stem]["fingerprint"] = "fp"
        m["photos"][stem]["artifacts"] = {f"{stem}_natural.tif": {"dep": stem}}
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")

    def render_one(stem, only=None):
        if stem == "P1":
            raise RuntimeError("rawtherapee exploded")

    monkeypatch.setattr(driver, "render_photo", render_one)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo",
                        lambda stem: {f"{stem}_natural.tif": {"dep": "new"}})
    collect = {}

    driver.process_all(force=True, collect=collect)

    saved = manifest.load()["photos"]
    assert saved["P1"]["state"] == "verified"
    assert saved["P1"]["artifacts"] == {"P1_natural.tif": {"dep": "P1"}}
    assert saved["P2"]["state"] == "verified"
    assert saved["P2"]["artifacts"] == {"P2_natural.tif": {"dep": "new"}}
    assert collect["failed"] == [
        {"stem": "P1", "code": "RENDER_FAILED",
         "message": "rawtherapee exploded"}]


def test_process_all_force_verify_failure_keeps_published_version(
        tmp_repo, monkeypatch):
    """The restore covers a failed verify, not just a raising render."""
    m = manifest.load()
    for stem in ("P1", "P2"):
        manifest.set_state(m, stem, "verified")
        m["photos"][stem]["fingerprint"] = "fp"
        m["photos"][stem]["artifacts"] = {f"{stem}_natural.tif": {"dep": stem}}
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo",
                        lambda stem: ["bad pixels"] if stem == "P1" else [])
    monkeypatch.setattr(driver, "_publish_photo",
                        lambda stem: {f"{stem}_natural.tif": {"dep": "new"}})
    collect = {}

    driver.process_all(force=True, collect=collect)

    saved = manifest.load()["photos"]
    assert saved["P1"]["state"] == "verified"
    assert saved["P1"]["artifacts"] == {"P1_natural.tif": {"dep": "P1"}}
    assert saved["P2"]["artifacts"] == {"P2_natural.tif": {"dep": "new"}}
    assert collect["failed"][0]["code"] == "VERIFY_FAILED"


def test_process_all_force_leaves_pre_approval_states_alone(
        tmp_repo, monkeypatch):
    m = manifest.load()
    manifest.set_state(m, "P1", "preview_ready")
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(
        driver, "render_photo",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError))

    driver.process_all(force=True)

    assert manifest.load()["photos"]["P1"]["state"] == "preview_ready"


def test_process_all_emits_render_verify_publish_stages(tmp_repo, monkeypatch):
    from pipeline import jsonio
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "fp"
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(driver, "render_photo", lambda stem, only=None: None)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo", lambda stem: {})
    events = []
    monkeypatch.setattr(jsonio, "emit", lambda e: events.append(e))

    driver.process_all()

    assert [e for e in events if e["event"] == "stage"] == [
        {"event": "stage", "stem": "P1", "stage": "render"},
        {"event": "stage", "stem": "P1", "stage": "verify"},
        {"event": "stage", "stem": "P1", "stage": "publish"},
    ]


def test_process_all_emits_preview_stage_and_per_style_progress(
        tmp_repo, monkeypatch):
    from pipeline import jsonio
    m = manifest.load()
    manifest.set_state(m, "P1", "ingested")
    manifest.save(m)
    monkeypatch.setattr(driver, "_current_fingerprint", lambda stem: "fp")
    monkeypatch.setattr(render, "ensure_sidecar_all", lambda stem: None)
    monkeypatch.setattr(driver, "preview_photo", lambda stem, style: None)
    events = []
    monkeypatch.setattr(jsonio, "emit", lambda e: events.append(e))
    collect = {}

    driver.process_all(collect=collect)

    assert events[0] == {"event": "stage", "stem": "P1", "stage": "preview"}
    assert events[1:] == [
        {"event": "progress", "stem": "P1", "stage": "preview",
         "index": index, "total": len(paths.STYLES), "detail": style}
        for index, style in enumerate(paths.STYLES, start=1)
    ]
    assert collect["advanced"] == [{"stem": "P1", "state": "preview_ready"}]


def test_finish_verified_reports_published_version_from_symlink(
        tmp_repo, monkeypatch):
    photo = tmp_repo / "Output/photos/P1"
    (photo / "v004").mkdir(parents=True)
    (photo / "current").symlink_to("v004")
    m = manifest.load()
    manifest.set_state(m, "P1", "rendered")
    manifest.save(m)
    monkeypatch.setattr(driver, "verify_photo", lambda stem: [])
    monkeypatch.setattr(driver, "_publish_photo",
                        lambda stem: {"a": {}, "b": {}, "c": {}})
    collect = {}

    assert driver._finish_verified(m, "P1", collect) is True

    assert collect["published"] == [
        {"stem": "P1", "version": "v004", "artifact_count": 3}]
