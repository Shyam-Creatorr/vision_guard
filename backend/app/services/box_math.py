def clamp_bbox_1000(bbox: list[int] | tuple[int, int, int, int]) -> list[int] | None:
    """
    Validates and clamps [ymin, xmin, ymax, xmax] to 0-1000 scale.
    Returns None for degenerate boxes (zero/negative or microscopic area).
    """
    if len(bbox) != 4:
        return None
    ymin, xmin, ymax, xmax = [max(0, min(1000, int(round(v)))) for v in bbox]
    if ymin >= ymax or xmin >= xmax:
        return None
    if (ymax - ymin) < 6 or (xmax - xmin) < 6:
        return None
    return [ymin, xmin, ymax, xmax]


def bbox_1000_to_pixels(bbox_1000: list[int], width_px: int, height_px: int) -> list[int]:
    """
    Converts [ymin, xmin, ymax, xmax] (0-1000) to pixel [x1, y1, x2, y2].
    """
    ymin, xmin, ymax, xmax = bbox_1000
    x1 = max(0, min(width_px - 1, int(round(xmin * width_px / 1000.0))))
    y1 = max(0, min(height_px - 1, int(round(ymin * height_px / 1000.0))))
    x2 = max(x1 + 1, min(width_px, int(round(xmax * width_px / 1000.0))))
    y2 = max(y1 + 1, min(height_px, int(round(ymax * height_px / 1000.0))))
    return [x1, y1, x2, y2]
