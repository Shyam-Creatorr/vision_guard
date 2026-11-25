from pathlib import Path

from app.schemas.analysis import (
    Agent1VisualAudit,
    Agent2GroundedExplanation,
    AuditedRegion,
    UnverifiedWarning,
)
from app.services.box_math import bbox_1000_to_pixels, clamp_bbox_1000
from app.services.legibility import evaluate_diagram_legibility
from app.services.suggestions import generate_closed_vocab_suggestions

ALLOWED_EXPLAIN_STATUSES = {"verified", "user_confirmed", "VERIFIED"}
BLOCKED_STATUSES = {"unverified_blocked", "suggested", "rejected", "UNVERIFIED"}


def is_allowed_status(status: str) -> bool:
    return status in ALLOWED_EXPLAIN_STATUSES


def apply_guardrail_lock(
    audit: Agent1VisualAudit,
    width_px: int,
    height_px: int,
    image_path: str | Path | None = None,
    global_blur_score: float | None = None,
    subject: str = "Biology",
    topic_hint: str | None = None,
) -> tuple[Agent1VisualAudit, list[str], list[str]]:
    """
    Deterministic server-side Guardrail Lock:
    1. Validates & clamps 0-1000 boxes, drops degenerate boxes, computes pixel coords.
    2. Runs region-level legibility pipeline (edge-masked sharpness, local contrast,
       RapidOCR confidence/agreement, border cutoff, and 8x8 unboxed blurry tile scan).
    3. Attaches closed-vocabulary CandidateSuggestions (marked as unverified guesses)
       to blocked regions.
    """
    cleaned_regions: list[AuditedRegion] = []
    verified_ids: list[str] = []
    unverified_ids: list[str] = []
    seen_ids: set[str] = set()

    leg_report = None
    if image_path is not None:
        leg_input = []
        for idx, region in enumerate(audit.regions, start=1):
            clamped = clamp_bbox_1000(region.bbox_1000)
            if clamped is None:
                continue
            bid = region.box_id.strip() or f"B{idx}"
            if bid in seen_ids:
                bid = f"{bid}_{idx}"
            seen_ids.add(bid)
            leg_input.append(
                {
                    "box_id": bid,
                    "label_text": region.label_text.strip(),
                    "component_type": region.component_type,
                    "bbox_1000": clamped,
                    "gemini_legible": region.status in ("VERIFIED", "verified", "user_confirmed"),
                    "confidence": region.confidence,
                }
            )
        leg_report = evaluate_diagram_legibility(
            image_path=image_path,
            regions=leg_input,
            global_blur_score=global_blur_score,
        )

        # Combine evaluated regions + unboxed blurry 8x8 tile clusters
        verified_labels = {
            r.label_text for r in leg_report.regions if r.status == "verified" and r.label_text
        }
        all_eval = list(leg_report.regions) + list(leg_report.unboxed_blur_regions)
        for ev in all_eval:
            if ev.status == "verified":
                cleaned_regions.append(
                    AuditedRegion(
                        box_id=ev.box_id,
                        label_text=ev.label_text,
                        component_type=ev.component_type,  # type: ignore[arg-type]
                        bbox_1000=ev.bbox_1000,
                        bbox_px=ev.bbox_px,
                        status="verified",
                        confidence=ev.legibility_score,
                        ambiguity_reason=None,
                        legibility_score=ev.legibility_score,
                        local_sharpness=ev.local_sharpness,
                        local_contrast=ev.local_contrast,
                        ocr_text=ev.ocr_text,
                        ocr_confidence=ev.ocr_confidence,
                        partially_blurry=ev.partially_blurry,
                    )
                )
                verified_ids.append(ev.box_id)
            else:
                reason = "; ".join(ev.reasons) if ev.reasons else "Region failed legibility gate"
                cands, no_rel = generate_closed_vocab_suggestions(
                    subject=subject,
                    topic_hint=topic_hint,
                    partial_ocr_text=ev.ocr_text,
                    already_verified_labels=verified_labels,
                )
                final_status = "suggested" if cands and not no_rel else "unverified_blocked"
                cleaned_regions.append(
                    AuditedRegion(
                        box_id=ev.box_id,
                        label_text="",  # Never leak unverified/guessed text as verified label
                        component_type=ev.component_type,  # type: ignore[arg-type]
                        bbox_1000=ev.bbox_1000,
                        bbox_px=ev.bbox_px,
                        status=final_status,  # type: ignore[arg-type]
                        confidence=ev.legibility_score,
                        ambiguity_reason=reason,
                        legibility_score=ev.legibility_score,
                        local_sharpness=ev.local_sharpness,
                        local_contrast=ev.local_contrast,
                        ocr_text=ev.ocr_text,
                        ocr_confidence=ev.ocr_confidence,
                        partially_blurry=ev.partially_blurry,
                        suggestions=cands,
                        no_reliable_suggestion=no_rel,
                    )
                )
                unverified_ids.append(ev.box_id)
    else:
        # Calibrated demo path (already verified/locked boxes without re-running OCR on synthetic crops)
        for idx, region in enumerate(audit.regions, start=1):
            clamped = clamp_bbox_1000(region.bbox_1000)
            if clamped is None:
                continue
            bid = region.box_id.strip() or f"B{idx}"
            if bid in seen_ids:
                bid = f"{bid}_{idx}"
            seen_ids.add(bid)
            px = bbox_1000_to_pixels(clamped, width_px, height_px)
            is_ver = region.status in ("VERIFIED", "verified", "user_confirmed") and (
                region.component_type != "label" or bool(region.label_text.strip())
            )
            status = "verified" if is_ver else "unverified_blocked"
            reason = None if is_ver else (region.ambiguity_reason or "Marked illegible during Visual Audit.")
            cleaned_regions.append(
                AuditedRegion(
                    box_id=bid,
                    label_text=region.label_text.strip() if is_ver else "",
                    component_type=region.component_type,
                    bbox_1000=clamped,
                    bbox_px=px,
                    status=status,  # type: ignore[arg-type]
                    confidence=round(region.confidence, 3),
                    ambiguity_reason=reason,
                    legibility_score=round(region.confidence, 3),
                )
            )
            if is_ver:
                verified_ids.append(bid)
            else:
                unverified_ids.append(bid)

    verified_set = set(verified_ids)
    cleaned_connections = [
        conn
        for conn in audit.connections
        if conn.from_box_id in seen_ids and conn.to_box_id in seen_ids
    ]
    for conn in cleaned_connections:
        if conn.from_box_id not in verified_set or conn.to_box_id not in verified_set:
            conn.status = "unverified_blocked"

    locked_audit = Agent1VisualAudit(
        diagram_summary=audit.diagram_summary,
        overall_legibility="poor" if (leg_report and leg_report.whole_image_blurry) or (not verified_ids and unverified_ids) else audit.overall_legibility,
        whole_image_blurry=bool(leg_report and leg_report.whole_image_blurry),
        retake_recommended=bool(leg_report and leg_report.retake_recommended),
        regions=cleaned_regions,
        connections=cleaned_connections,
    )
    return locked_audit, verified_ids, unverified_ids


def enforce_strict_status_guardrail(
    agent2: Agent2GroundedExplanation,
    region_statuses: dict[str, str],
) -> Agent2GroundedExplanation:
    """
    Programmatic backend guardrail:
    ONLY regions with status 'verified' or 'user_confirmed' may appear in explanation steps or practice prompts.
    Anything 'unverified_blocked', 'suggested', or 'rejected' is strictly stripped before leaving the server.
    """
    allowed_ids = {bid for bid, st in region_statuses.items() if is_allowed_status(st)}
    user_confirmed_ids = {bid for bid, st in region_statuses.items() if st == "user_confirmed"}

    safe_steps = []
    for step in agent2.steps:
        if step.cited_box_id in allowed_ids:
            step.confirmed_by_user = step.cited_box_id in user_confirmed_ids
            safe_steps.append(step)
    for i, step in enumerate(safe_steps, start=1):
        step.step_number = i

    safe_practice = [
        item for item in agent2.practice_prompts if item.box_id in allowed_ids
    ]

    return Agent2GroundedExplanation(
        title=agent2.title,
        language=agent2.language,
        limited_mode=agent2.limited_mode,
        limited_mode_notice=agent2.limited_mode_notice,
        steps=safe_steps,
        rubric=agent2.rubric,
        unverified_warnings=agent2.unverified_warnings,
        practice_prompts=safe_practice,
    )


def enforce_agent2_guardrails(
    agent2: Agent2GroundedExplanation,
    locked_audit: Agent1VisualAudit,
    verified_ids: list[str],
) -> Agent2GroundedExplanation:
    status_map = {r.box_id: r.status for r in locked_audit.regions}
    for vid in verified_ids:
        status_map.setdefault(vid, "verified")

    guarded = enforce_strict_status_guardrail(agent2, status_map)
    existing_warn_ids = {w.box_id for w in guarded.unverified_warnings}
    warnings = list(guarded.unverified_warnings)

    for region in locked_audit.regions:
        if not is_allowed_status(region.status) and region.box_id not in existing_warn_ids:
            hint = region.ocr_text or f"{region.component_type.title()} near {region.bbox_1000}"
            reason = region.ambiguity_reason or "Region failed legibility check"
            warnings.append(
                UnverifiedWarning(
                    box_id=region.box_id,
                    region_hint=hint,
                    reason=reason,
                    warning_message=(
                        f"Region {region.box_id} is locked ({reason}) and excluded from explanations and quizzes."
                    ),
                )
            )

    guarded.unverified_warnings = warnings
    return guarded
