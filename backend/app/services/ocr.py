from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_ocr_engine() -> RapidOCR:
    return RapidOCR()


def detect_text_regions(image_path: str | Path) -> list[dict[str, Any]]:
    """
    Runs local RapidOCR on the full diagram image.
    Returns list of {text, confidence, bbox_1000, bbox_px}.
    """
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        return []
    h, w = bgr.shape[:2]
    engine = _get_ocr_engine()
    result, _ = engine(bgr)
    if not result:
        return []

    detections: list[dict[str, Any]] = []
    for item in result:
        poly, text, conf = item
        xs = [float(p[0]) for p in poly]
        ys = [float(p[1]) for p in poly]
        x1 = max(0, min(w - 1, int(min(xs))))
        y1 = max(0, min(h - 1, int(min(ys))))
        x2 = max(x1 + 1, min(w, int(max(xs))))
        y2 = max(y1 + 1, min(h, int(max(ys))))
        bbox_1000 = [
            int(round(y1 * 1000 / h)),
            int(round(x1 * 1000 / w)),
            int(round(y2 * 1000 / h)),
            int(round(x2 * 1000 / w)),
        ]
        detections.append(
            {
                "text": str(text).strip(),
                "confidence": float(conf),
                "bbox_1000": bbox_1000,
                "bbox_px": [x1, y1, x2, y2],
            }
        )
    return detections


def ocr_region_crop(bgr_crop: np.ndarray) -> tuple[str, float, int]:
    """
    Runs RapidOCR on a cropped label/region patch.
    Upscales only moderately small crops (height 24..64px) while preserving tiny-text detection.
    Returns (combined_text, avg_confidence, estimated_text_height_px).
    """
    if bgr_crop is None or bgr_crop.size == 0:
        return "", 0.0, 0

    ch, cw = bgr_crop.shape[:2]
    if ch < 12 or cw < 12:
        return "", 0.0, 0

    # Measure raw foreground stroke height before any upscaling
    gray = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2GRAY)
    # Trim 10% border to ignore pill outline
    py = max(2, int(ch * 0.12))
    px = max(2, int(cw * 0.08))
    inner = gray[py : max(py + 1, ch - py), px : max(px + 1, cw - px)]
    est_height = 0
    if inner.size > 0:
        _, bw = cv2.threshold(inner, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        row_counts = np.sum(bw > 0, axis=1)
        active_rows = np.where(row_counts >= max(2, inner.shape[1] * 0.03))[0]
        if active_rows.size > 0:
            est_height = int(active_rows[-1] - active_rows[0] + 1)

    engine = _get_ocr_engine()
    # Add light padding around crop so RapidOCR detector can frame words cleanly
    padded = cv2.copyMakeBorder(bgr_crop, 16, 16, 16, 16, cv2.BORDER_REPLICATE)
    result, _ = engine(padded)
    if not result:
        return "", 0.0, est_height

    texts: list[str] = []
    confs: list[float] = []
    for item in result:
        _, txt, conf = item
        if str(txt).strip():
            texts.append(str(txt).strip())
            confs.append(float(conf))

    if not texts:
        return "", 0.0, est_height
    return " ".join(texts), float(sum(confs) / len(confs)), est_height
