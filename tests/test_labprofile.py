import pytest

from pipeline import labprofile


def test_load_generic_v1():
    p = labprofile.load("generic-v1")
    assert p["jpeg_quality"] == 92
    assert p["ppi"] == 300
    assert p["safe_edge_percent"] == 2


def test_field_classes_partition():
    all_fields = labprofile.REVIEW_FIELDS | labprofile.RENDER_FIELDS | labprofile.ORDER_FIELDS
    p = labprofile.load("generic-v1")
    assert set(p.keys()) == all_fields


def test_views():
    p = labprofile.load("generic-v1")
    assert set(labprofile.review_view(p)) == labprofile.REVIEW_FIELDS
    assert set(labprofile.render_view(p)) == labprofile.RENDER_FIELDS


def test_missing_field_raises(tmp_repo):
    (tmp_repo / "config/lab-profiles/broken.yaml").write_text("jpeg_quality: 92\n")
    with pytest.raises(ValueError):
        labprofile.load("broken")


def test_check_filename():
    p = labprofile.load("generic-v1")
    assert labprofile.check_filename("P1_natural.jpg", p) is None
    assert labprofile.check_filename("x" * 70 + ".jpg", p) is not None
    assert labprofile.check_filename("café.jpg", p) is not None
