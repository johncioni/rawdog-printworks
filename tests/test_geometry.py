import pytest
from pipeline import geometry


def test_target_pixels():
    assert geometry.target_pixels("8x10", False, 300) == (2400, 3000)
    assert geometry.target_pixels("8x10", True, 300) == (3000, 2400)
    assert geometry.target_pixels("5x7", False, 300) == (1500, 2100)
    assert geometry.target_pixels("5x7", True, 300) == (2100, 1500)


def test_centered_norm_roundtrip():
    n = geometry.centered_crop_norm(5776, 4336, "8x10", True)
    px = geometry.to_pixels(n, 5776, 4336)
    assert px["h"] == 4336 and px["w"] == 5420   # 4336*10/8
    assert px["x"] == (5776 - 5420) // 2 and px["y"] == 0
    geometry.validate_crop(n, 5776, 4336, "8x10", True, 300)  # no raise


def test_subject_crop_shifts_window_toward_off_left_bbox_center():
    centered = geometry.centered_crop_norm(5776, 4336, "8x10", True)
    bbox = {"x": 0.05, "y": 0.35, "w": 0.2, "h": 0.2}

    subject = geometry.subject_crop_norm(
        5776, 4336, "8x10", True, bbox
    )

    assert subject["x"] < centered["x"]
    assert subject["y"] == centered["y"]


def test_subject_crop_clamps_window_flush_to_frame_edges():
    left = geometry.subject_crop_norm(
        5776, 4336, "8x10", True,
        {"x": 0.0, "y": 0.0, "w": 0.02, "h": 0.02},
    )
    right = geometry.subject_crop_norm(
        5776, 4336, "8x10", True,
        {"x": 0.98, "y": 0.98, "w": 0.02, "h": 0.02},
    )

    assert left["x"] == 0.0
    assert left["y"] == 0.0
    assert right["x"] + right["w"] == pytest.approx(1.0)
    assert right["y"] + right["h"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    "bbox",
    [
        {"x": 0.4, "y": 0.4, "w": 0.0, "h": 0.0},
        {"x": -0.5, "y": -0.5, "w": 2.0, "h": 2.0},
    ],
)
def test_subject_crop_degenerate_or_huge_bbox_still_validates(bbox):
    subject = geometry.subject_crop_norm(
        5776, 4336, "8x10", True, bbox
    )

    geometry.validate_crop(
        subject, 5776, 4336, "8x10", True, 300
    )


def test_validate_rejects_out_of_bounds():
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0.9, "y": 0.0, "w": 0.5, "h": 1.0},
                               5776, 4336, "8x10", True, 300)


def test_validate_rejects_upscale():
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0.0, "y": 0.0, "w": 0.3, "h": 0.3},
                               5776, 4336, "8x10", True, 300)


def test_validate_respects_ppi():
    n = geometry.centered_crop_norm(5776, 4336, "8x10", True)
    with pytest.raises(ValueError):                # 600 PPI needs 6000x4800
        geometry.validate_crop(n, 5776, 4336, "8x10", True, 600)


def test_validate_rejects_degenerate_window():
    # 0.0001 * 4336 rounds to 0 pixels tall; must be a ValueError, never a
    # ZeroDivisionError from the aspect check dividing by px["h"].
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0.0, "y": 0.0, "w": 0.8, "h": 0.0001},
                               5776, 4336, "8x10", True, 300)


def test_validate_rejects_window_that_rounds_past_the_edge():
    # x + w = 1.00008 in normalized space, but rounds to 1156 + 4621 = 5777
    # pixels on a 5776-wide source: one pixel past the right edge. Height is
    # aspect-correct so this reaches the bounds check on its own merits.
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": 0.20008, "y": 0.0, "w": 0.8, "h": 3697/4336},
                               5776, 4336, "8x10", True, 300)


def test_validate_rejects_negative_normalized_origin():
    # x is outside normalized [0, 1] but rounds to pixel 0, so the pixel-space
    # bounds check alone accepts it. The normalized contract must reject it.
    with pytest.raises(ValueError):
        geometry.validate_crop({"x": -0.00004, "y": 0.0, "w": 5420/5776, "h": 1.0},
                               5776, 4336, "8x10", True, 300)


def test_pdf_page_inches():
    assert geometry.pdf_page_inches("8x10", 2400, 3000, 300, False) == (8.0, 10.0)
    assert geometry.pdf_page_inches(None, 5776, 4336, 300, True) == (5776/300, 4336/300)
