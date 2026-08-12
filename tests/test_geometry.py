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


def test_pdf_page_inches():
    assert geometry.pdf_page_inches("8x10", 2400, 3000, 300, False) == (8.0, 10.0)
    assert geometry.pdf_page_inches(None, 5776, 4336, 300, True) == (5776/300, 4336/300)
