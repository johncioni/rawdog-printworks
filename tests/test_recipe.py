from pipeline import geometry, recipe

LOCK = {"rawtherapee": {"path": "/x", "version": "5.12", "sha256": "aa"},
        "rt_icc": {"path": "/z", "version": "asset", "sha256": "cc"},
        "magick": {"path": "/y", "version": "7.1", "sha256": "bb"}}
LAB = {"safe_edge_percent": 2, "bleed": "none", "color_space": "srgb", "ppi": 300,
       "jpeg_quality": 92, "submission_format": "jpeg", "embed_icc": True,
       "max_file_bytes": 1, "filename_rules": "x",
       "strip_metadata_beyond_allowlist": True, "keep_capture_date": True,
       "lab_color_correction": "off", "checkout_crop_review": "required"}


def _fp(rec, lock=LOCK, lab=LAB):
    return recipe.fingerprint("P1", rec, {"natural": "s1"}, "seed1", lock, lab)


def test_fingerprint_stable_and_sensitive():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    assert _fp(rec) == _fp(rec)                      # deterministic
    rec2 = recipe.new("P1", "rawhash", 5776, 4336)
    rec2["crops"]["8x10"] = geometry.centered_crop_norm(5776, 4336, "8x10", True)
    assert _fp(rec) != _fp(rec2)                     # crop change breaks it


def test_fingerprint_ignores_order_fields():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    lab2 = dict(LAB, lab_color_correction="on")      # order-only field
    assert _fp(rec) == _fp(rec, lab=lab2)


def test_fingerprint_sensitive_to_render_tool():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    lock2 = {**LOCK, "rawtherapee": {**LOCK["rawtherapee"], "sha256": "zz"}}
    assert _fp(rec) != _fp(rec, lock=lock2)
    lock3 = {**LOCK, "rt_icc": {**LOCK["rt_icc"], "sha256": "zz"}}
    assert _fp(rec) != _fp(rec, lock=lock3)


def test_fingerprint_insensitive_to_verify_tool():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    lock2 = {**LOCK, "magick": {**LOCK["magick"], "sha256": "zz"}}
    assert _fp(rec) == _fp(rec, lock=lock2)


def test_fingerprint_sensitive_to_manual_assets():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    a = _fp(rec)
    rec["manual_assets"].append({"file": "P1_retouch.tif", "sha256": "mm"})
    assert _fp(rec) != a


def test_new_records_source_dimensions_and_defaults():
    rec = recipe.new("P1", "rawhash", 5776, 4336)
    assert (rec["width"], rec["height"]) == (5776, 4336)
    assert rec["manual_assets"] == []
    assert rec["crops"] == {"8x10": None, "5x7": None}
    assert rec["sharpen"] == recipe.DEFAULT_SHARPEN
    rec["sharpen"]["native"] = "changed"
    rec["manual_assets"].append({"file": "f", "sha256": "h"})
    fresh = recipe.new("P1", "rawhash", 5776, 4336)
    assert fresh["sharpen"] == recipe.DEFAULT_SHARPEN
    assert fresh["manual_assets"] == []


def test_file_hashes(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello")
    assert recipe.file_hashes([p]) == {
        "a.txt": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"}


def test_save_load_roundtrip(tmp_repo):
    rec = recipe.new("P1036163", "rawhash", 5776, 4336)
    rec["crops"]["5x7"] = geometry.centered_crop_norm(5776, 4336, "5x7", True)
    rec["manual_assets"].append({"file": "P1036163_retouch.tif", "sha256": "mm"})
    recipe.save("P1036163", rec)
    assert recipe.load("P1036163") == rec
