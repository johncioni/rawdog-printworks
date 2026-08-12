import json

import yaml

from pipeline import manifest, recipe

LOCK = {"rawtherapee": {"sha256": "aa"}, "magick": {"sha256": "bb"},
        "img2pdf": {"sha256": "cc"}}
LAB = {"jpeg_quality": 92, "submission_format": "jpeg", "embed_icc": True,
       "max_file_bytes": 1, "filename_rules": "x",
       "strip_metadata_beyond_allowlist": True, "keep_capture_date": True}


def test_artifact_names_count():
    names = manifest.artifact_names("P1")
    assert len(names) == 22
    assert len(set(names)) == 22
    assert "P1_natural.tif" in names and "P1_bw_5x7.jpg" in names
    assert "P1_filmic_8x10.pdf" in names and "P1_comparison.pdf" in names


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
