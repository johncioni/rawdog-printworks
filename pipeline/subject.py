import os

import Quartz
import Vision


def _warn(image_path, error):
    print(f"WARNING: face detection failed for {image_path}: {error}")


def group_bbox(image_path):
    try:
        image_path = os.path.abspath(os.fspath(image_path))
        image_url = Quartz.CFURLCreateWithFileSystemPath(
            None,
            image_path,
            Quartz.kCFURLPOSIXPathStyle,
            False,
        )
        request = Vision.VNDetectFaceRectanglesRequest.alloc().init()
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(
            image_url, {}
        )
        succeeded, error = handler.performRequests_error_([request], None)
        if not succeeded:
            _warn(image_path, error)
            return None

        faces = request.results() or ()
        if not faces:
            return None

        boxes = []
        for face in faces:
            bounds = face.boundingBox()
            width = float(bounds.size.width)
            height = float(bounds.size.height)
            boxes.append({
                "x": float(bounds.origin.x),
                "y": 1.0 - float(bounds.origin.y) - height,
                "w": width,
                "h": height,
            })

        mean_width = sum(box["w"] for box in boxes) / len(boxes)
        mean_height = sum(box["h"] for box in boxes) / len(boxes)
        left = max(0.0, min(box["x"] for box in boxes) - mean_width)
        top = max(0.0, min(box["y"] for box in boxes) - 1.5 * mean_height)
        right = min(
            1.0,
            max(box["x"] + box["w"] for box in boxes) + mean_width,
        )
        bottom = min(
            1.0,
            max(box["y"] + box["h"] for box in boxes)
            + 1.5 * mean_height,
        )
        return {
            "x": left,
            "y": top,
            "w": right - left,
            "h": bottom - top,
        }
    except Exception as error:
        _warn(image_path, error)
        return None
