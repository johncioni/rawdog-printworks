SIZES = {"8x10": (8, 10), "5x7": (5, 7)}


def target_pixels(crop, landscape, ppi):
    a, b = SIZES[crop]
    return (b * ppi, a * ppi) if landscape else (a * ppi, b * ppi)


def centered_crop_norm(w, h, crop, landscape):
    tw, th = target_pixels(crop, landscape, 300)
    aspect = tw / th
    if w / h > aspect:
        ch, cw = h, round(h * aspect)
    else:
        cw, ch = w, round(w / aspect)
    return {"x": (w - cw) / 2 / w, "y": (h - ch) / 2 / h, "w": cw / w, "h": ch / h}


def to_pixels(n, w, h):
    return {"x": round(n["x"] * w), "y": round(n["y"] * h),
            "w": round(n["w"] * w), "h": round(n["h"] * h)}


def validate_crop(n, w, h, crop, landscape, ppi):
    if not (0 <= n["x"] and 0 <= n["y"] and n["x"] + n["w"] <= 1.0001
            and n["y"] + n["h"] <= 1.0001):
        raise ValueError(f"crop window out of bounds: {n}")
    px = to_pixels(n, w, h)
    tw, th = target_pixels(crop, landscape, ppi)
    if abs((px["w"] / px["h"]) - (tw / th)) / (tw / th) > 0.005:
        raise ValueError(f"crop window aspect mismatch: {px}")
    if px["w"] < tw or px["h"] < th:
        raise ValueError(f"crop window would require upscaling at {ppi} PPI: {px}")


def pdf_page_inches(crop, w, h, ppi, landscape):
    if crop is None:
        return (w / ppi, h / ppi)
    a, b = SIZES[crop]
    return (float(b), float(a)) if landscape else (float(a), float(b))
