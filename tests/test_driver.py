import hashlib
from pathlib import Path

import pytest

from pipeline import (crops, driver, geometry, manifest, metadata, paths, pdfs,
                      publish, recipe, render, toolchain)


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
