from pathlib import Path
from typing import Literal
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import get_settings
from app.schemas.analysis import (
    Agent1VisualAudit,
    Agent2GroundedExplanation,
    AuditedRegion,
    DemoDiagramInfo,
    DiagramConnection,
    ExplanationStep,
    PracticePromptItem,
    RubricComparison,
    UnverifiedWarning,
)

DemoSlug = Literal["plant_cell", "human_heart", "water_cycle"]


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _draw_label_pill(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    blur: bool = False,
) -> None:
    if blur:
        patch = Image.new("RGB", (w, h), (255, 248, 232))
        pdraw = ImageDraw.Draw(patch)
        pdraw.rounded_rectangle([2, 2, w - 3, h - 3], radius=12, fill=(255, 240, 200), outline=(204, 138, 0), width=2)
        pdraw.text((14, max(8, h // 4)), text, fill=(74, 79, 84), font=_font(20))
        patch = patch.filter(ImageFilter.GaussianBlur(radius=4.5))
        img.paste(patch, (x, y))
        return
    draw.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=(255, 255, 255), outline=(14, 15, 16), width=3)
    draw.text((x + 14, y + max(8, (h - 22) // 2)), text, fill=(14, 15, 16), font=_font(22))


def ensure_demo_image(slug: DemoSlug) -> Path:
    settings = get_settings()
    demo_dir = settings.upload_path.parent / "demos"
    demo_dir.mkdir(parents=True, exist_ok=True)
    out_path = demo_dir / f"{slug}.png"
    if out_path.exists():
        return out_path

    W, H = 1200, 800
    img = Image.new("RGB", (W, H), (246, 240, 227))
    draw = ImageDraw.Draw(img)

    if slug == "plant_cell":
        draw.text((48, 30), "Eukaryotic Plant Cell Cross-Section", fill=(14, 15, 16), font=_font(30))
        # Cell Wall & Membrane
        draw.rounded_rectangle([220, 120, 980, 700], radius=72, fill=(181, 217, 74), outline=(94, 122, 0), width=14)
        draw.rounded_rectangle([250, 150, 950, 670], radius=56, fill=(238, 247, 214), outline=(141, 182, 0), width=6)
        # Central Vacuole
        draw.rounded_rectangle([420, 230, 740, 560], radius=90, fill=(191, 230, 250), outline=(58, 143, 194), width=5)
        # Nucleus
        draw.ellipse([755, 260, 915, 420], fill=(255, 217, 122), outline=(204, 138, 0), width=5)
        draw.ellipse([805, 310, 865, 370], fill=(204, 138, 0))
        # Chloroplast
        draw.ellipse([285, 230, 410, 325], fill=(141, 182, 0), outline=(94, 122, 0), width=4)
        # Mitochondria
        draw.ellipse([290, 475, 425, 560], fill=(255, 182, 39), outline=(204, 138, 0), width=4)

        # Leader lines + exact labels matching bbox_1000
        draw.line([(205, 180), (245, 180)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 30, 150, 180, 54, "Cell Wall")

        draw.line([(230, 275), (285, 275)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 30, 248, 200, 54, "Chloroplast")

        draw.line([(235, 520), (290, 520)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 25, 492, 210, 54, "Mitochondria")

        draw.line([(740, 410), (960, 480)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 960, 450, 215, 54, "Central Vacuole")

        draw.line([(915, 330), (985, 240)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 980, 205, 180, 54, "Nucleus")

        # Intentional blurry/cut-off label in corner -> UNVERIFIED
        _draw_label_pill(draw, img, 965, 650, 230, 54, "Golgi Smudge", blur=True)

    elif slug == "human_heart":
        draw.text((48, 30), "Human Heart Chambers & Blood Flow", fill=(14, 15, 16), font=_font(30))
        # Aorta arch
        draw.arc([480, 110, 740, 350], start=180, end=360, fill=(204, 138, 0), width=36)
        # Heart chambers
        draw.rounded_rectangle([380, 220, 600, 410], radius=36, fill=(191, 230, 250), outline=(58, 143, 194), width=5)
        draw.rounded_rectangle([380, 410, 600, 640], radius=50, fill=(126, 200, 240), outline=(58, 143, 194), width=5)
        draw.rounded_rectangle([605, 220, 820, 410], radius=36, fill=(255, 217, 122), outline=(204, 138, 0), width=5)
        draw.rounded_rectangle([605, 410, 820, 640], radius=50, fill=(255, 182, 39), outline=(204, 138, 0), width=5)

        draw.line([(250, 290), (380, 290)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 36, 262, 215, 54, "Right Atrium")

        draw.line([(250, 520), (380, 520)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 30, 492, 225, 54, "Right Ventricle")

        draw.line([(820, 290), (945, 290)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 945, 262, 200, 54, "Left Atrium")

        draw.line([(820, 520), (945, 520)], fill=(14, 15, 16), width=3)
        _draw_label_pill(draw, img, 945, 492, 215, 54, "Left Ventricle")

        _draw_label_pill(draw, img, 540, 88, 135, 52, "Aorta")
        _draw_label_pill(draw, img, 40, 690, 240, 54, "Vena Cava Faint", blur=True)

    else:  # water_cycle
        draw.text((48, 30), "Hydrologic Water Cycle", fill=(14, 15, 16), font=_font(30))
        # Sun
        draw.ellipse([80, 100, 210, 230], fill=(255, 182, 39), outline=(204, 138, 0), width=5)
        # Cloud
        draw.ellipse([440, 120, 680, 230], fill=(255, 255, 255), outline=(58, 143, 194), width=5)
        draw.ellipse([540, 100, 770, 225], fill=(255, 255, 255), outline=(58, 143, 194), width=5)
        # Mountain & Ocean
        draw.polygon([(700, 540), (920, 280), (1120, 540)], fill=(181, 217, 74), outline=(94, 122, 0), width=5)
        draw.rectangle([80, 540, 760, 700], fill=(126, 200, 240), outline=(58, 143, 194), width=5)

        # Arrows
        draw.line([(290, 520), (390, 250)], fill=(204, 138, 0), width=6)
        draw.line([(720, 235), (860, 320)], fill=(58, 143, 194), width=6)
        draw.line([(860, 450), (650, 560)], fill=(94, 122, 0), width=6)

        _draw_label_pill(draw, img, 175, 360, 210, 54, "Evaporation")
        _draw_label_pill(draw, img, 500, 140, 230, 54, "Condensation")
        _draw_label_pill(draw, img, 855, 190, 220, 54, "Precipitation")
        _draw_label_pill(draw, img, 745, 515, 240, 54, "Surface Runoff")
        _draw_label_pill(draw, img, 945, 675, 235, 54, "Groundwater Blur", blur=True)

    img.save(out_path, format="PNG")
    return out_path


_DEMO_SPECS = {
    "plant_cell": {
        "title": "Eukaryotic Plant Cell Cross-Section",
        "subject": "Biology",
        "default_question": "Explain the key organelles visible in this plant cell diagram and compare my notes.",
        "default_reference": "Plant cells have a rigid cell wall for support, chloroplasts that perform photosynthesis, mitochondria for ATP energy, a nucleus holding DNA, and a large central vacuole.",
        "regions": [
            ("B1", "Cell Wall", "label", [188, 25, 255, 175], "VERIFIED", 0.98, None),
            ("B2", "Chloroplast", "label", [310, 25, 378, 192], "VERIFIED", 0.97, None),
            ("B3", "Mitochondria", "label", [615, 21, 682, 196], "VERIFIED", 0.96, None),
            ("B4", "Central Vacuole", "label", [562, 800, 630, 979], "VERIFIED", 0.97, None),
            ("B5", "Nucleus", "label", [256, 816, 324, 967], "VERIFIED", 0.98, None),
            ("B6", "", "label", [812, 804, 880, 996], "UNVERIFIED", 0.28, "Label in bottom-right corner is blurred and illegible."),
        ],
        "hints": {
            "B1": ("Rigid outer cellulose layer providing structural support.", ["Cell Membrane", "Cytoplasm", "Ribosome"]),
            "B2": ("Green plastid containing chlorophyll where photosynthesis occurs.", ["Lysosome", "Centriole", "Golgi Body"]),
            "B3": ("Organelle that generates ATP through cellular respiration.", ["Vacuole", "Nucleolus", "Peroxisome"]),
            "B4": ("Large fluid-filled sac maintaining turgor pressure in plant cells.", ["Smooth ER", "Plasmodesmata", "Ribosome"]),
            "B5": ("Membrane-bound organelle housing the cell's genetic DNA.", ["Chloroplast", "Cell Wall", "Cytosol"]),
        },
    },
    "human_heart": {
        "title": "Human Heart Chambers & Blood Flow",
        "subject": "Biology",
        "default_question": "Walk through how blood moves across the verified chambers of the human heart.",
        "default_reference": "Deoxygenated blood enters the right atrium and moves to the right ventricle; oxygenated blood from the lungs enters the left atrium, moves to the left ventricle, and exits via the aorta.",
        "regions": [
            ("B1", "Right Atrium", "label", [328, 30, 395, 209], "VERIFIED", 0.97, None),
            ("B2", "Right Ventricle", "label", [615, 25, 682, 212], "VERIFIED", 0.96, None),
            ("B3", "Left Atrium", "label", [328, 788, 395, 954], "VERIFIED", 0.97, None),
            ("B4", "Left Ventricle", "label", [615, 788, 682, 967], "VERIFIED", 0.98, None),
            ("B5", "Aorta", "label", [110, 450, 175, 562], "VERIFIED", 0.96, None),
            ("B6", "", "label", [862, 33, 930, 233], "UNVERIFIED", 0.31, "Lower-left vessel label is smudged and unreadable."),
        ],
        "hints": {
            "B1": ("Upper right chamber receiving deoxygenated blood from the body.", ["Left Ventricle", "Pulmonary Vein", "Septum"]),
            "B2": ("Lower right chamber pumping blood toward the lungs.", ["Aorta", "Left Atrium", "Mitral Valve"]),
            "B3": ("Upper left chamber receiving oxygen-rich blood from the lungs.", ["Right Atrium", "Vena Cava", "Right Ventricle"]),
            "B4": ("Thick-walled lower left chamber pumping oxygenated blood to the body.", ["Right Ventricle", "Pulmonary Artery", "Right Atrium"]),
            "B5": ("Main systemic artery arching out of the left ventricle.", ["Superior Vena Cava", "Trachea", "Bronchus"]),
        },
    },
    "water_cycle": {
        "title": "Hydrologic Water Cycle",
        "subject": "Earth Science",
        "default_question": "Trace the verified stages of water movement from ocean to atmosphere and land.",
        "default_reference": "Solar heat causes evaporation from oceans, water vapor cools into condensation forming clouds, falls as precipitation, and returns via surface runoff.",
        "regions": [
            ("B1", "Evaporation", "label", [450, 146, 518, 321], "VERIFIED", 0.97, None),
            ("B2", "Condensation", "label", [175, 417, 242, 608], "VERIFIED", 0.98, None),
            ("B3", "Precipitation", "label", [238, 712, 305, 896], "VERIFIED", 0.96, None),
            ("B4", "Surface Runoff", "label", [644, 621, 711, 821], "VERIFIED", 0.95, None),
            ("B5", "", "label", [844, 788, 911, 983], "UNVERIFIED", 0.25, "Bottom-right underground label is blurry and cut near edge."),
        ],
        "hints": {
            "B1": ("Solar heating turns liquid surface water into rising water vapor.", ["Transpiration", "Sublimation", "Infiltration"]),
            "B2": ("Cooling water vapor forms droplets and clouds in the atmosphere.", ["Evaporation", "Runoff", "Percolation"]),
            "B3": ("Water falls from clouds back to Earth as rain or snow.", ["Condensation", "Evaporation", "Aquifer"]),
            "B4": ("Flow of rainwater across land back toward rivers and oceans.", ["Condensation", "Precipitation", "Freezing"]),
        },
    },
}


def list_demos() -> list[DemoDiagramInfo]:
    out: list[DemoDiagramInfo] = []
    for slug, spec in _DEMO_SPECS.items():
        ensure_demo_image(slug)  # type: ignore[arg-type]
        regions = spec["regions"]
        out.append(
            DemoDiagramInfo(
                slug=slug,  # type: ignore[arg-type]
                title=spec["title"],
                subject=spec["subject"],
                default_question=spec["default_question"],
                default_reference=spec["default_reference"],
                verified_count=sum(1 for r in regions if r[4] == "VERIFIED"),
                unverified_count=sum(1 for r in regions if r[4] == "UNVERIFIED"),
                image_url=f"/api/v1/analyses/demos/{slug}/image",
            )
        )
    return out


def _translate_step(label: str, hint: str, language: str, idx: int) -> tuple[str, str]:
    if language == "hi":
        return (
            f"चरण {idx}: {label}",
            f"सत्यापित क्षेत्र '{label}' की पुष्टि आरेख से हुई है। कार्य: {hint}",
        )
    if language == "kn":
        return (
            f"ಹಂತ {idx}: {label}",
            f"ದೃಢೀಕೃತ ಭಾಗ '{label}' ಚಿತ್ರದಲ್ಲಿ ಸ್ಪಷ್ಟವಾಗಿದೆ. ವಿವರಣೆ: {hint}",
        )
    return (f"{label}", hint)


def _score_reference(reference_answer: str | None, verified_labels: list[str]) -> RubricComparison | None:
    if not reference_answer or not reference_answer.strip():
        return None
    lower_ref = reference_answer.lower()
    matched = [lbl for lbl in verified_labels if lbl.lower() in lower_ref]
    missing = [lbl for lbl in verified_labels if lbl.lower() not in lower_ref]
    misconceptions: list[str] = []
    if "animal cell" in lower_ref and "Cell Wall" in verified_labels:
        misconceptions.append("Mentions animal cell, but this diagram contains a Plant Cell Wall and Chloroplast.")
    if "deoxygenated" in lower_ref and "left ventricle" in lower_ref and "aorta" in lower_ref and "oxygenated" not in lower_ref:
        misconceptions.append("Note that the Left Ventricle pumps oxygenated blood into the Aorta.")
    total = max(1, len(verified_labels))
    raw_score = round((len(matched) / total) * 10.0, 1)
    if misconceptions:
        raw_score = max(0.0, round(raw_score - 1.0, 1))
    return RubricComparison(
        score_out_of_10=raw_score,
        matched_concepts=matched,
        missing_details=missing,
        misconceptions=misconceptions,
        feedback_summary=(
            f"Matched {len(matched)}/{total} verified diagram concepts."
            + (f" Missing: {', '.join(missing)}." if missing else " Complete coverage of verified regions!")
        ),
    )


def build_demo_pipeline_outputs(
    slug: DemoSlug,
    reference_answer: str | None,
    language: str,
) -> tuple[Agent1VisualAudit, Agent2GroundedExplanation, Path]:
    img_path = ensure_demo_image(slug)
    spec = _DEMO_SPECS[slug]

    regions = [
        AuditedRegion(
            box_id=r[0],
            label_text=r[1],
            component_type=r[2],
            bbox_1000=list(r[3]),
            status=r[4],
            confidence=r[5],
            ambiguity_reason=r[6],
        )
        for r in spec["regions"]
    ]

    audit = Agent1VisualAudit(
        diagram_summary=f"{spec['title']} audited with {len(regions)} detected regions.",
        overall_legibility="partial",
        regions=regions,
        connections=[],
    )

    verified_regions = [r for r in regions if r.status == "VERIFIED"]
    unverified_regions = [r for r in regions if r.status == "UNVERIFIED"]
    hints = spec["hints"]

    steps: list[ExplanationStep] = []
    prompts: list[PracticePromptItem] = []
    for idx, reg in enumerate(verified_regions, start=1):
        hint_def, distractors = hints[reg.box_id]
        heading, expl = _translate_step(reg.label_text, hint_def, language, idx)
        steps.append(
            ExplanationStep(
                step_number=idx,
                heading=heading,
                explanation=expl,
                cited_box_id=reg.box_id,
                confidence_badge="high" if reg.confidence >= 0.9 else "medium",
            )
        )
        prompts.append(
            PracticePromptItem(
                box_id=reg.box_id,
                expected_label=reg.label_text,
                definition_hint=hint_def,
                distractors=distractors,
            )
        )

    warnings = [
        UnverifiedWarning(
            box_id=r.box_id,
            region_hint=f"Region at {r.bbox_1000}",
            reason=r.ambiguity_reason or "Illegible",
            warning_message=f"Region {r.box_id} could not be verified ({r.ambiguity_reason}) and is locked from explanation.",
        )
        for r in unverified_regions
    ]

    rubric = _score_reference(reference_answer, [r.label_text for r in verified_regions])
    agent2 = Agent2GroundedExplanation(
        title=spec["title"],
        language=language,  # type: ignore[arg-type]
        steps=steps,
        rubric=rubric,
        unverified_warnings=warnings,
        practice_prompts=prompts,
    )
    return audit, agent2, img_path


def build_offline_upload_audit(
    image_path: str | Path,
    blur_score: float,
    question: str,
    reference_answer: str | None,
    language: str,
    title: str,
) -> tuple[Agent1VisualAudit, Agent2GroundedExplanation]:
    """
    Honest Limited Mode (when GEMINI_API_KEY is unconfigured or model unavailable):
    Runs local RapidOCR + morphological label-pill box detection (no fabricated labels!),
    then passes candidate boxes to apply_guardrail_lock (legibility + 8x8 blurry tiles).
    Produces ZERO fake explanation steps.
    """
    from app.services.ocr import detect_text_regions

    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Image could not be loaded for Limited Mode audit.")
    h, w = bgr.shape[:2]

    ocr_hits = detect_text_regions(image_path)
    regions: list[AuditedRegion] = []
    idx = 1

    # Filter out top diagram title banner (first ~8% height) and keep label detections
    for hit in ocr_hits:
        ymin, xmin, ymax, xmax = hit["bbox_1000"]
        if ymin < 75:
            continue
        regions.append(
            AuditedRegion(
                box_id=f"B{idx}",
                label_text=hit["text"],
                component_type="label",
                bbox_1000=[ymin, xmin, ymax, xmax],
                status="VERIFIED" if hit["confidence"] >= 0.55 else "UNVERIFIED",
                confidence=round(hit["confidence"], 3),
                ambiguity_reason=None if hit["confidence"] >= 0.55 else "Low local OCR confidence",
            )
        )
        idx += 1

    # Locate white/light label pills missed by OCR (e.g., blurred/occluded/low-contrast pills)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bright = (gray > 246).astype(np.uint8) * 255
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True):
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < max(55, w * 0.06) or ch < max(24, h * 0.03) or ch > h * 0.14 or cw > w * 0.35:
            continue
        ymin = int(y * 1000 / h)
        xmin = int(x * 1000 / w)
        ymax = int((y + ch) * 1000 / h)
        xmax = int((x + cw) * 1000 / w)
        if ymin < 75:
            continue
        # Skip if overlaps >= 35% of the smaller box (IoMin) with an existing OCR region
        overlaps = False
        for r in regions:
            ry1, rx1, ry2, rx2 = r.bbox_1000
            ix = max(0, min(xmax, rx2) - max(xmin, rx1))
            iy = max(0, min(ymax, ry2) - max(ymin, ry1))
            area_new = max(1, (ymax - ymin) * (xmax - xmin))
            area_old = max(1, (ry2 - ry1) * (rx2 - rx1))
            if (ix * iy) / min(area_new, area_old) > 0.35:
                overlaps = True
                break
        if overlaps:
            continue
        regions.append(
            AuditedRegion(
                box_id=f"B{idx}",
                label_text="",
                component_type="label",
                bbox_1000=[ymin, xmin, ymax, xmax],
                status="UNVERIFIED",
                confidence=0.25,
                ambiguity_reason="Label could not be read by local OCR",
            )
        )
        idx += 1
        if idx > 14:
            break

    if not regions and blur_score < 45.0:
        regions.append(
            AuditedRegion(
                box_id="B1",
                label_text="",
                component_type="region",
                bbox_1000=[150, 150, 850, 850],
                status="UNVERIFIED",
                confidence=0.2,
                ambiguity_reason=f"Whole diagram failed sharpness gate (blur {blur_score:.1f} < 45).",
            )
        )

    audit = Agent1VisualAudit(
        diagram_summary="Audited in Limited Mode (local OCR + OpenCV legibility checks; AI explanations disabled).",
        overall_legibility="poor" if blur_score < 45.0 else "partial",
        regions=regions,
        connections=[],
    )

    agent2 = Agent2GroundedExplanation(
        title=title,
        language=language,  # type: ignore[arg-type]
        limited_mode=True,
        limited_mode_notice=(
            "Limited Mode active (no GEMINI_API_KEY configured): Only local OCR-verified labels are marked Verified. "
            "No AI explanations are generated; Practice Mode remains available for verified and user-confirmed labels."
        ),
        steps=[],
        rubric=None,
        unverified_warnings=[],
        practice_prompts=[
            PracticePromptItem(
                box_id=r.box_id,
                expected_label=r.label_text,
                definition_hint=f"OCR-confirmed label '{r.label_text}'",
                distractors=[],
            )
            for r in regions
            if r.status == "VERIFIED" and r.label_text.strip()
        ],
    )
    return audit, agent2
