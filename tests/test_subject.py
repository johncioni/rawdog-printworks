import pytest

from pipeline import paths, subject


def _vision_unavailable():
    """Probe framework availability only, so a real detection failure on a
    capable machine still fails the test instead of being skipped."""
    try:
        import Quartz
        import Vision

        space = Quartz.CGColorSpaceCreateDeviceRGB()
        context = Quartz.CGBitmapContextCreate(
            None,
            1,
            1,
            8,
            4,
            space,
            Quartz.kCGImageAlphaPremultipliedFirst
            | Quartz.kCGBitmapByteOrder32Little,
        )
        image = Quartz.CGBitmapContextCreateImage(context)
        request = Vision.VNDetectFaceRectanglesRequest.alloc().init()
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
            image, {}
        )
        succeeded, _ = handler.performRequests_error_([request], None)
        return not succeeded
    except Exception:
        return True


requires_vision = pytest.mark.skipif(
    _vision_unavailable(),
    reason="Vision unavailable in this environment",
)


@requires_vision
def test_group_bbox_detects_real_group():
    preview = paths.previews_dir() / "P1036163_natural_preview.jpg"
    if not preview.is_file():
        # previews/ is gitignored live photo data, so it exists only in the
        # main checkout — never in a fresh worktree or CI. A missing input is
        # not a detection failure; where the file is present this still fails
        # loudly rather than skipping.
        pytest.skip(f"preview fixture not present: {preview}")

    bbox = subject.group_bbox(preview)

    assert bbox is not None
    assert all(0.0 <= bbox[key] <= 1.0 for key in ("x", "y", "w", "h"))
    assert bbox["x"] + bbox["w"] <= 1.0
    assert bbox["y"] + bbox["h"] <= 1.0
    assert 0.3 <= bbox["x"] + bbox["w"] / 2 <= 0.7
    assert 0.2 <= bbox["y"] + bbox["h"] / 2 <= 0.8
