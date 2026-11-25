from dataclasses import dataclass
from pathlib import Path
import uuid

import cv2
import numpy as np

from app.core.config import get_settings


@dataclass
class PreprocessOutcome:
    normalized_key: str
    width_px: int
    height_px: int
    blur_score: float
    contrast_score: float
    quality_status: str  # "pass" | "warn" | "fail"
    quality_notes: list[str]
    recommend_retake: bool


def analyze_and_normalize_diagram(image_path: str | Path) -> PreprocessOutcome:
    """
    Runs OpenCV blur (Laplacian variance), RMS contrast, resolution check,
    and writes a normalized CLAHE-enhanced working PNG.
    """
    settings = get_settings()
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"OpenCV could not read image at {image_path}")

    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    blur_score = float(round(cv2.Laplacian(gray, cv2.CV_64F).var(), 2))
    # Diagrams often have 80%+ clean white background; use p99-p1 ink-to-paper dynamic range
    p_high, p_low = np.percentile(gray, [99.2, 0.8])
    contrast_score = float(round(float(p_high - p_low) / 2.55, 2))  # 0-100 scale

    notes: list[str] = []
    severity = 0  # 0=pass, 1=warn, 2=fail(retake recommended)

    min_dim = min(width, height)
    if min_dim < 320:
        severity = max(severity, 2)
        notes.append(f"Resolution is low ({width}x{height}px). Small labels may lock as UNVERIFIED.")
    elif min_dim < 600:
        severity = max(severity, 1)
        notes.append(f"Moderate resolution ({width}x{height}px). Higher resolution improves label accuracy.")

    if blur_score < 45.0:
        severity = max(severity, 2)
        notes.append(
            f"Significant blur detected (score {blur_score} < 45). Retake photo or illegible regions will be locked UNVERIFIED."
        )
    elif blur_score < 95.0:
        severity = max(severity, 1)
        notes.append(f"Mild blur detected (score {blur_score}). Faint text may be marked UNVERIFIED.")

    if contrast_score < 12.0:
        severity = max(severity, 2)
        notes.append(f"Very low contrast (score {contrast_score} < 12). Retake in brighter, even lighting.")
    elif contrast_score < 20.0:
        severity = max(severity, 1)
        notes.append("Low contrast detected — automatic CLAHE illumination normalization applied.")

    if not notes:
        notes.append("Sharp focus, strong contrast, and clear resolution detected.")

    # Gentle CLAHE illumination normalization on LAB L-channel (preserves colors, sharpens ink)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    l_norm = clahe.apply(l_ch)
    norm_bgr = cv2.cvtColor(cv2.merge((l_norm, a_ch, b_ch)), cv2.COLOR_LAB2BGR)

    upload_dir = settings.upload_path
    upload_dir.mkdir(parents=True, exist_ok=True)
    normalized_key = f"{uuid.uuid4().hex}_norm.png"
    norm_path = upload_dir / normalized_key
    cv2.imwrite(str(norm_path), norm_bgr)

    quality_status = "fail" if severity == 2 else ("warn" if severity == 1 else "pass")
    return PreprocessOutcome(
        normalized_key=normalized_key,
        width_px=width,
        height_px=height,
        blur_score=blur_score,
        contrast_score=contrast_score,
        quality_status=quality_status,
        quality_notes=notes,
        recommend_retake=(severity == 2),
    )
