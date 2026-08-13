import json

import yaml

from pipeline import manifest, paths, recipe

LOCK = {"rawtherapee": {"sha256": "aa"}, "magick": {"sha256": "bb"},
        "img2pdf": {"sha256": "cc"}}
# Every class present, so a record that wrongly pulls in a whole class shows up.
FULL_LOCK = {"rawtherapee": {"sha256": "aa"}, "rt_icc": {"sha256": "ii"},
             "magick": {"sha256": "bb"}, "font": {"sha256": "ff"},
             "img2pdf": {"sha256": "cc"}, "qpdf": {"sha256": "dd"},
             "pdfimages": {"sha256": "ee"}, "pdfinfo": {"sha256": "gg"},
             "exiftool": {"sha256": "hh"}}
LAB = {"jpeg_quality": 92, "submission_format": "jpeg", "embed_icc": True,
       "max_file_bytes": 1, "filename_rules": "x",
       "strip_metadata_beyond_allowlist": True, "keep_capture_date": True,
       "ppi": 300}
STYLE_HASHES = {"natural": "s", "filmic": "f", "bw": "b", "vibrant": "v"}


def _deps(artifact, rec=None, style_hashes=None, lock=FULL_LOCK, lab=LAB,
          crop=None):
    rec = rec if rec is not None else recipe.new("P1", "raw", 5776, 4336)
    return manifest.artifact_deps("P1", artifact, rec,
                                  style_hashes or STYLE_HASHES, "seed", lock,
                                  lab, crop)


def test_artifact_names_count():
    names = manifest.artifact_names("P1")
    assert len(names) == 29
    assert len(set(names)) == 29
    assert names[:4] == [f"P1_{style}.tif" for style in paths.STYLES]
    assert "P1_natural.tif" in names and "P1_bw_5x7.jpg" in names
    assert "P1_filmic_8x10.pdf" in names and "P1_comparison.pdf" in names
    assert {
        "P1_vibrant.tif",
        "P1_vibrant.jpg",
        "P1_vibrant_8x10.jpg",
        "P1_vibrant_5x7.jpg",
        "P1_vibrant.pdf",
        "P1_vibrant_8x10.pdf",
        "P1_vibrant_5x7.pdf",
    } <= set(names)


def test_state_downgrade_on_fingerprint_change(tmp_repo):
    m = manifest.load()
    manifest.set_state(m, "P1", "approved")
    m["photos"]["P1"]["fingerprint"] = "old"
    assert manifest.effective_state(m, "P1", "old") == "approved"
    assert manifest.effective_state(m, "P1", "new") == "review_required"


def test_early_states_not_downgraded(tmp_repo):
    m = manifest.load()
    manifest.set_state(m, "P1", "preview_ready")
    m["photos"]["P1"]["fingerprint"] = None
    assert manifest.effective_state(m, "P1", "anything") == "preview_ready"


def test_deps_differ_between_tif_and_jpg():
    rec = recipe.new("P1", "raw", 5776, 4336)
    tif = manifest.artifact_deps("P1", "P1_natural.tif", rec,
                                 {"natural": "s"}, "seed", LOCK, LAB, None)
    jpg = manifest.artifact_deps("P1", "P1_natural_8x10.jpg", rec,
                                 {"natural": "s"}, "seed", LOCK, LAB,
                                 {"x": 0, "y": 0, "w": 10, "h": 8})
    assert "magick" not in str(tif) and "magick" in str(jpg)
    assert tif != jpg


def test_tif_record_tracks_overrides():
    on = recipe.new("P1", "raw", 5776, 4336)
    on["overrides"]["denoise"] = True
    tif = _deps("P1_natural.tif")
    assert tif["overrides"] == {"denoise": False}
    assert _deps("P1_natural.tif", rec=on) != tif


def test_raster_records_track_ppi():
    jpg = _deps("P1_natural_8x10.jpg", crop={"x": 0})
    assert jpg["ppi"] == 300
    assert _deps("P1_natural_8x10.jpg", lab={**LAB, "ppi": 360},
                 crop={"x": 0}) != jpg
    assert "ppi" in _deps("P1_natural_8x10.pdf", crop={"x": 0})
    assert "ppi" not in _deps("P1_natural.tif")


def test_pdf_record_is_strict_superset_of_its_jpg():
    jpg = _deps("P1_natural_8x10.jpg", crop={"x": 0})
    pdf = _deps("P1_natural_8x10.pdf", crop={"x": 0})
    assert pdf.items() >= jpg.items()
    assert pdf != jpg


def test_font_only_stales_the_comparison_sheet():
    # The font is only drawn on the sheet, so carrying it in every JPG and PDF
    # record would stale all of them on a font update.
    assert "font" not in str(_deps("P1_natural_8x10.jpg", crop={"x": 0}))
    assert "font" not in str(_deps("P1_natural.pdf"))
    assert "font" in str(_deps("P1_comparison.pdf"))


def test_verify_only_tools_are_in_no_record():
    for name in manifest.artifact_names("P1"):
        blob = str(_deps(name, crop={"x": 0}))
        for tool in ("qpdf", "pdfimages", "pdfinfo"):
            assert tool not in blob, f"{tool} leaked into {name}"


def test_exiftool_belongs_to_pdf_records_only():
    # wrap() rewrites document info with exiftool after img2pdf, so it shapes
    # PDF bytes; the rasters it never touches must not carry it.
    for name in manifest.artifact_names("P1"):
        blob = str(_deps(name, crop={"x": 0}))
        assert ("exiftool" in blob) == name.endswith(".pdf"), name


def test_exiftool_drift_stales_pdfs_but_not_jpgs():
    drifted = {**FULL_LOCK, "exiftool": {"sha256": "h2"}}
    for pdf, jpg in (("P1_natural_8x10.pdf", "P1_natural_8x10.jpg"),
                     ("P1_comparison.pdf", "P1_natural.jpg")):
        assert _deps(pdf, lock=drifted, crop={"x": 0}) != _deps(
            pdf, crop={"x": 0})
        assert _deps(jpg, lock=drifted, crop={"x": 0}) == _deps(
            jpg, crop={"x": 0})


def test_stem_containing_a_style_token_parses():
    rec = recipe.new("P_bw_1", "raw", 5776, 4336)
    deps = manifest.artifact_deps("P_bw_1", "P_bw_1_natural_8x10.jpg", rec,
                                  STYLE_HASHES, "seed", FULL_LOCK, LAB,
                                  {"x": 0})
    assert deps["style"] == "s"
    assert deps["sharpen"] == recipe.DEFAULT_SHARPEN["8x10"]


def test_sheet_embeds_source_records_and_stales_with_them(tmp_repo):
    sheet = _deps("P1_comparison.pdf")
    assert sheet["sources"]["P1_natural.jpg"] == _deps("P1_natural.jpg")
    assert sheet["sources"]["P1_vibrant.jpg"] == _deps("P1_vibrant.jpg")
    m = manifest.load()
    manifest.set_state(m, "P1", "rendered")
    manifest.record_artifacts(m, "P1", {"P1_comparison.pdf": sheet})
    moved = _deps("P1_comparison.pdf",
                  style_hashes={**STYLE_HASHES, "natural": "s2"})
    assert manifest.stale_artifacts(m, "P1", {"P1_comparison.pdf": moved}) == [
        "P1_comparison.pdf"]


def test_record_and_stale(tmp_repo):
    m = manifest.load()
    manifest.set_state(m, "P1", "rendered")
    manifest.record_artifacts(m, "P1", {"P1_natural.tif": {"d": 1},
                                        "P1_natural.jpg": {"d": 2}})
    stale = manifest.stale_artifacts(m, "P1", {"P1_natural.tif": {"d": 1},
                                               "P1_natural.jpg": {"d": 9}})
    assert stale == ["P1_natural.jpg"]


def test_rebuild_from_recipes_and_provenance(tmp_repo):
    (tmp_repo / "recipes/P1.yaml").write_text(yaml.safe_dump(
        {"approval": {"fingerprint": "fp", "approved_at": "t"}}))
    cur = tmp_repo / "Output/photos/P1/v001"
    cur.mkdir(parents=True)
    (cur / "provenance.json").write_text(json.dumps(
        {"fingerprint": "fp", "artifacts": {"P1_natural.tif": {"d": 1}}}))
    (tmp_repo / "Output/photos/P1/current").symlink_to("v001")
    m = manifest.rebuild()
    assert m["photos"]["P1"]["state"] == "verified"
    assert m["photos"]["P1"]["artifacts"]["P1_natural.tif"] == {"d": 1}


def test_load_readonly_never_writes_manifest(tmp_repo):
    from pipeline import manifest, paths, recipe
    recipe.save("P1", recipe.new("P1", "aa" * 32, 5776, 4336))
    assert not paths.manifest_path().exists()
    m = manifest.load_readonly()
    assert "P1" in m["photos"]
    assert not paths.manifest_path().exists()          # the point


def test_save_is_atomic_no_partial_file_on_same_name(tmp_repo):
    from pipeline import manifest, paths
    manifest.save({"photos": {}})
    # os.replace leaves no sibling temp files behind
    leftovers = [p for p in paths.root().iterdir()
                 if p.name.startswith(".manifest.") ]
    assert leftovers == []
