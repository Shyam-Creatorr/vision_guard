from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.core.config import get_settings
from app.services.box_math import bbox_1000_to_pixels, clamp_bbox_1000
from app.services.ocr import ocr_region_crop


@dataclass
class RegionLegibility:
    box_id: str
    label_text: str
    component_type: str
    bbox_1000: list[int]
    bbox_px: list[int]
    status: str  # verified | unverified_blocked | suggested | user_confirmed | rejected
    legibility_score: float
    local_sharpness: float
    local_contrast: float
    ocr_text: str
    ocr_confidence: float
    ocr_agreement: float
    is_flat_color: bool
    partially_blurry: bool
    reasons: list[str]


@dataclass
class DiagramLegibilityReport:
    regions: list[RegionLegibility]
    unboxed_blur_regions: list[RegionLegibility]
    whole_image_blurry: bool
    retake_recommended: bool
    sharp_reference_median: float
    flagged_tile_count: int
    total_edge_tiles: int


def _inner_crop(gray: np.ndarray, bgr: np.ndarray, px: list[int]) -> tuple[np.ndarray, np.ndarray]:
    x1, y1, x2, y2 = px
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    # Trim outer 12% so pill/box borders do not spoof sharpness on blurred/tiny/low-contrast text inside
    mx = max(2, int(w * 0.08))
    my = max(2, int(h * 0.14))
    ix1 = min(x2 - 2, x1 + mx)
    iy1 = min(y2 - 2, y1 + my)
    ix2 = max(ix1 + 2, x2 - mx)
    iy2 = max(iy1 + 2, y2 - my)
    return gray[iy1:iy2, ix1:ix2], bgr[iy1:iy2, ix1:ix2]


def _edge_masked_sharpness(inner_gray: np.ndarray) -> tuple[float, float, float]:
    """
    Returns (edge_density, edge_laplacian_var, jpeg_blockiness_ratio).
    Flat-color regions have very low edge_density and are NOT penalized as blurry.
    """
    if inner_gray.size == 0 or min(inner_gray.shape[:2]) < 6:
        return 0.0, 0.0, 0.0

    gx = cv2.Sobel(inner_gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(inner_gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_mag = np.sqrt(gx * gx + gy * gy)
    edge_mask = grad_mag > 22.0
    edge_density = float(np.mean(edge_mask))

    if edge_density < 0.008:
        return edge_density, 0.0, 0.0

    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(edge_mask.astype(np.uint8), kernel, iterations=1) > 0
    lap = cv2.Laplacian(inner_gray, cv2.CV_64F)
    vals = lap[dilated]
    lap_var = float(np.var(vals)) if vals.size > 0 else 0.0

    # Directional motion-blur check: if horizontal/vertical gradient energy is strongly skewed (>3.2x), penalize
    ex = float(np.mean(np.abs(gx[dilated]))) + 1e-5
    ey = float(np.mean(np.abs(gy[dilated]))) + 1e-5
    anisotropy = max(ex / ey, ey / ex)
    if anisotropy > 3.0:
        lap_var *= 0.25

    # 8x8 JPEG block boundary artifact check (periodic grid jumps, not a single vector border line)
    h, w = inner_gray.shape[:2]
    blockiness = 0.0
    if h >= 16 and w >= 16 and lap_var < 6000.0:
        f = inner_gray.astype(np.float64)
        h_diff = np.abs(np.diff(f, axis=1))
        if h_diff.shape[1] >= 16:
            b_cols = h_diff[:, 7::8]
            nb_cols = np.delete(h_diff, slice(7, h_diff.shape[1], 8), axis=1)
            # Require periodic grid energy across multiple blocks (quantile 75), not 1 isolated line
            b_q = float(np.percentile(b_cols, 75)) if b_cols.size else 0.0
            nb_q = float(np.percentile(nb_cols, 75)) + 1e-5
            b_mean = float(np.mean(b_cols)) if b_cols.size else 0.0
            nb_mean = float(np.mean(nb_cols)) + 1e-5
            if b_mean > nb_mean * 1.55 and b_mean > 4.0 and b_q > nb_q * 1.25:
                blockiness = min(1.0, (b_mean / nb_mean - 1.3) / 1.5)

    return edge_density, lap_var, blockiness


def _local_contrast(inner_gray: np.ndarray) -> float:
    if inner_gray.size == 0:
        return 0.0
    p_high, p_low = np.percentile(inner_gray, [96, 4])
    return float(max(0.0, min(1.0, (p_high - p_low) / 220.0)))


def _occlusion_ratio(inner_gray: np.ndarray) -> float:
    """Detects dark solid tape/smudge bars occluding a large fraction of the label interior."""
    if inner_gray.size == 0:
        return 0.0
    dark_ratio = float(np.mean(inner_gray < 65))
    return dark_ratio


def _text_similarity(a: str, b: str) -> float:
    na = " ".join(a.lower().split())
    nb = " ".join(b.lower().split())
    if not na or not nb:
        return 0.0
    return float(SequenceMatcher(None, na, nb).ratio())


def evaluate_diagram_legibility(
    image_path: str | Path,
    regions: list[dict[str, Any]],
    global_blur_score: float | None = None,
) -> DiagramLegibilityReport:
    """
    Computes region-level legibility scores (0-1) combining:
      (a) Edge-masked Laplacian sharpness normalized against sharp image tiles (flat-color safe)
      (b) Local text-vs-background contrast
      (c) Local RapidOCR confidence + text agreement
      (d) Gemini per-label legibility flag
      (e) Image-border cut-off check
    Plus an 8x8 tile grid scan for unboxed blurry regions.
    """
    settings = get_settings()
    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError(f"Cannot read image at {image_path}")
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 1. 8x8 tile grid scan to calibrate sharp reference median & find unboxed blurry tiles
    grid = settings.LEGIBILITY_TILE_GRID
    tile_h = max(1, h // grid)
    tile_w = max(1, w // grid)
    edge_tile_sharpness: list[float] = []
    tile_stats: list[tuple[int, int, float, float, float, float]] = []

    for gy_i in range(grid):
        for gx_i in range(grid):
            y1 = gy_i * tile_h
            x1 = gx_i * tile_w
            y2 = h if gy_i == grid - 1 else (gy_i + 1) * tile_h
            x2 = w if gx_i == grid - 1 else (gx_i + 1) * tile_w
            t_gray = gray[y1:y2, x1:x2]
            ed, lap_v, blk = _edge_masked_sharpness(t_gray)
            con = _local_contrast(t_gray)
            tile_stats.append((gy_i, gx_i, ed, lap_v, con, blk))
            if ed >= 0.015:
                edge_tile_sharpness.append(lap_v)

    if edge_tile_sharpness:
        sorted_sh = sorted(edge_tile_sharpness)
        top_half = sorted_sh[len(sorted_sh) // 2 :]
        sharp_ref = float(np.median(top_half))
    else:
        sharp_ref = 150.0
    # Cap reference so ultra-crisp text strokes don't cause smooth vector curves to fail
    sharp_ref = max(150.0, min(1100.0, sharp_ref))

    flagged_tiles: set[tuple[int, int]] = set()
    total_edge_tiles = 0
    for gy_i, gx_i, ed, lap_v, con, blk in tile_stats:
        if ed < 0.022:
            continue
        total_edge_tiles += 1
        norm_sh = min(1.0, lap_v / (sharp_ref * 0.35))
        if norm_sh < settings.LEGIBILITY_MIN_SHARPNESS_NORM or blk > 0.38:
            flagged_tiles.add((gy_i, gx_i))

    whole_image_blurry = (
        total_edge_tiles == 0
        or (len(flagged_tiles) / total_edge_tiles) >= 0.72
        or (global_blur_score is not None and global_blur_score < 45.0)
    )

    # Merge adjacent flagged tiles into unboxed blurry regions (only when not whole-image blurry)
    unboxed_blur_regions: list[RegionLegibility] = []
    visited: set[tuple[int, int]] = set()
    if not whole_image_blurry:
        cluster_idx = 1
        for tile in sorted(flagged_tiles):
            if tile in visited:
                continue
            stack = [tile]
            cluster: list[tuple[int, int]] = []
            while stack:
                cur = stack.pop()
                if cur in visited or cur not in flagged_tiles:
                    continue
                visited.add(cur)
                cluster.append(cur)
                cy, cx = cur
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nxt = (cy + dy, cx + dx)
                    if nxt in flagged_tiles and nxt not in visited:
                        stack.append(nxt)
            min_y = min(c[0] for c in cluster) * tile_h
            min_x = min(c[1] for c in cluster) * tile_w
            max_y = min(h, (max(c[0] for c in cluster) + 1) * tile_h)
            max_x = min(w, (max(c[1] for c in cluster) + 1) * tile_w)
            b1000 = [
                int(round(min_y * 1000 / h)),
                int(round(min_x * 1000 / w)),
                int(round(max_y * 1000 / h)),
                int(round(max_x * 1000 / w)),
            ]
            unboxed_blur_regions.append(
                RegionLegibility(
                    box_id=f"UB{cluster_idx}",
                    label_text="",
                    component_type="region",
                    bbox_1000=b1000,
                    bbox_px=[min_x, min_y, max_x, max_y],
                    status="unverified_blocked",
                    legibility_score=0.22,
                    local_sharpness=0.18,
                    local_contrast=0.4,
                    ocr_text="",
                    ocr_confidence=0.0,
                    ocr_agreement=0.0,
                    is_flat_color=False,
                    partially_blurry=True,
                    reasons=["Blurry area detected by 8x8 tile scan"],
                )
            )
            cluster_idx += 1

    # 2. Evaluate every boxed region
    evaluated: list[RegionLegibility] = []
    for idx, reg in enumerate(regions, start=1):
        clamped = clamp_bbox_1000(reg["bbox_1000"])
        if clamped is None:
            continue
        box_id = str(reg.get("box_id") or f"B{idx}").strip()
        label_text = str(reg.get("label_text") or "").strip()
        comp_type = str(reg.get("component_type") or "label")
        gemini_legible = bool(reg.get("gemini_legible", True))

        px = bbox_1000_to_pixels(clamped, w, h)
        inner_gray, inner_bgr = _inner_crop(gray, bgr, px)
        ed, lap_v, blk = _edge_masked_sharpness(inner_gray)
        con = _local_contrast(inner_gray)
        occ = _occlusion_ratio(inner_gray)

        # Flat-color interior structures must NOT be blocked as blurry
        is_flat_color = (comp_type == "structure" and ed < 0.012 and occ < 0.35)
        sharp_norm = 1.0 if is_flat_color else min(1.0, lap_v / (sharp_ref * 0.40))
        if blk > 0.30:
            sharp_norm = min(sharp_norm, max(0.0, 0.35 - blk * 0.5))

        ocr_text, ocr_conf, est_text_h = ocr_region_crop(bgr[px[1] : px[3], px[0] : px[2]])
        agreement = _text_similarity(ocr_text, label_text) if (ocr_text and label_text) else (1.0 if not label_text else 0.0)

        reasons: list[str] = []
        ymin, xmin, ymax, xmax = clamped
        border_cutoff = (ymin <= 3 or xmin <= 3 or ymax >= 997 or xmax >= 997)

        if not gemini_legible:
            reasons.append("AI auditor flagged region as illegible")
        if border_cutoff:
            reasons.append("Label is cut off at the edge")
        if not is_flat_color and sharp_norm < settings.LEGIBILITY_MIN_SHARPNESS_NORM:
            reasons.append("Text is blurred")
        if blk > 0.30:
            reasons.append("Heavy JPEG compression artifacts degrade text")
        if occ > 0.34 and comp_type == "label":
            reasons.append("Region is partially occluded")
        if not is_flat_color and con < settings.LEGIBILITY_MIN_CONTRAST:
            reasons.append("Low contrast text")

        if comp_type == "label":
            if est_text_h > 0 and est_text_h < 10 and ocr_conf < 0.72:
                reasons.append("Text is too small to read reliably")
            if not ocr_text or ocr_conf < 0.52:
                reasons.append("OCR could not verify text legibility")
            elif label_text and agreement < settings.LEGIBILITY_OCR_AGREE_MIN:
                reasons.append("OCR and AI disagree on label text")

        # Overlap with flagged 8x8 blurry tiles -> mark partially_blurry metadata;
        # only block if region itself lacks strong sharpness + OCR confirmation
        partially_blurry = False
        for ub in unboxed_blur_regions:
            ux1, uy1, ux2, uy2 = ub.bbox_px
            if min(px[2], ux2) > max(px[0], ux1) and min(px[3], uy2) > max(px[1], uy1):
                partially_blurry = True
                break
        if partially_blurry and not is_flat_color and (sharp_norm < 0.55 or (comp_type == "label" and ocr_conf < 0.75)):
            if "Text is blurred" not in reasons:
                reasons.append("Overlaps partially blurry area")

        # Combined Legibility Score (0-1)
        if is_flat_color:
            combined = 0.92
        else:
            ocr_sig = (ocr_conf * 0.5 + agreement * 0.5) if comp_type == "label" else 0.85
            combined = (
                0.35 * sharp_norm
                + 0.25 * min(1.0, con / 0.45)
                + 0.30 * ocr_sig
                + 0.10 * (1.0 if gemini_legible else 0.0)
            )
            if border_cutoff or occ > 0.34 or blk > 0.30:
                combined = min(combined, 0.32)
            if whole_image_blurry:
                combined = min(combined, 0.25)

        combined = round(max(0.0, min(1.0, combined)), 3)

        should_block = (
            bool(reasons)
            or combined < settings.LEGIBILITY_BLOCK_THRESHOLD
        )
        # Do not block clean flat-color structures unless borderline/flagged by Gemini
        if is_flat_color and gemini_legible and not border_cutoff:
            should_block = False
            reasons = []

        evaluated.append(
            RegionLegibility(
                box_id=box_id,
                label_text=label_text,
                component_type=comp_type,
                bbox_1000=clamped,
                bbox_px=px,
                status="unverified_blocked" if should_block else "verified",
                legibility_score=combined,
                local_sharpness=round(sharp_norm, 3),
                local_contrast=round(con, 3),
                ocr_text=ocr_text,
                ocr_confidence=round(ocr_conf, 3),
                ocr_agreement=round(agreement, 3),
                is_flat_color=is_flat_color,
                partially_blurry=partially_blurry,
                reasons=reasons,
            )
        )

    return DiagramLegibilityReport(
        regions=evaluated,
        unboxed_blur_regions=unboxed_blur_regions,
        whole_image_blurry=whole_image_blurry,
        retake_recommended=whole_image_blurry,
        sharp_reference_median=round(sharp_ref, 2),
        flagged_tile_count=len(flagged_tiles),
        total_edge_tiles=total_edge_tiles,
    )
