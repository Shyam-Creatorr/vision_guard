import json
from pathlib import Path
import pytest

FIX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "degraded"


def test_bug1_degraded_recall_and_flat_color_non_blocking():
    """
    Failing test (pre-fix):
    - Recall across all 8 degraded fixtures must be >= 0.90.
    - False-block rate on clean fixtures + B_FLAT solid-color areas must be <= 0.10.
    """
    from app.services.legibility import evaluate_diagram_legibility  # new module to implement

    gt = json.loads((FIX_DIR / "ground_truth.json").read_text())

    tp = 0
    fn = 0
    clean_total = 0
    clean_fp = 0

    for item in gt:
        deg_path = FIX_DIR / item["degraded_file"]
        clean_path = FIX_DIR / item["clean_file"]
        regions = item["regions"]
        degraded_ids = set(item["degraded_box_ids"])

        # 1. Degraded fixture check
        deg_report = evaluate_diagram_legibility(
            image_path=deg_path,
            regions=[
                {
                    "box_id": r["box_id"],
                    "label_text": r["label_text"],
                    "component_type": "structure" if r["flat"] else "label",
                    "bbox_1000": r["bbox_1000"],
                    "gemini_legible": True,
                    "confidence": 0.92,
                }
                for r in regions
            ],
        )
        blocked_ids = {r.box_id for r in deg_report.regions if r.status == "unverified_blocked"}
        for bid in degraded_ids:
            if bid in blocked_ids:
                tp += 1
            else:
                fn += 1
        assert "B_FLAT" not in blocked_ids, f"Flat color region falsely blocked in {item['fixture']}"

        # 2. Clean fixture check
        clean_report = evaluate_diagram_legibility(
            image_path=clean_path,
            regions=[
                {
                    "box_id": r["box_id"],
                    "label_text": r["label_text"],
                    "component_type": "structure" if r["flat"] else "label",
                    "bbox_1000": r["bbox_1000"],
                    "gemini_legible": True,
                    "confidence": 0.92,
                }
                for r in regions
                if not r["flat"] and not (item["degradation_type"] == "cutoff_border" and r["box_id"] == "B3")
            ],
        )
        for cr in clean_report.regions:
            clean_total += 1
            if cr.status == "unverified_blocked":
                clean_fp += 1

    recall = tp / max(1, tp + fn)
    false_block_rate = clean_fp / max(1, clean_total)
    assert recall >= 0.90, f"Degraded recall {recall:.2f} < 0.90 (tp={tp}, fn={fn})"
    assert false_block_rate <= 0.10, f"Clean false-block rate {false_block_rate:.2f} > 0.10"


def test_bug1_status_enum_and_guardrail_rejects_unconfirmed():
    from app.schemas.analysis import Agent2GroundedExplanation, ExplanationStep, PracticePromptItem
    from app.services.guardrail import enforce_strict_status_guardrail

    allowed_statuses = {"verified", "unverified_blocked", "suggested", "user_confirmed", "rejected"}
    assert "user_confirmed" in allowed_statuses

    # Only verified or user_confirmed may enter steps / quiz
    region_statuses = {
        "B1": "verified",
        "B2": "unverified_blocked",
        "B3": "suggested",
        "B4": "user_confirmed",
        "B5": "rejected",
    }
    raw_a2 = Agent2GroundedExplanation(
        title="Cell",
        language="en",
        steps=[
            ExplanationStep(step_number=1, heading="S1", explanation="Ok", cited_box_id="B1"),
            ExplanationStep(step_number=2, heading="S2", explanation="Blocked", cited_box_id="B2"),
            ExplanationStep(step_number=3, heading="S3", explanation="Guess", cited_box_id="B3"),
            ExplanationStep(step_number=4, heading="S4", explanation="User", cited_box_id="B4"),
            ExplanationStep(step_number=5, heading="S5", explanation="Rej", cited_box_id="B5"),
        ],
        practice_prompts=[
            PracticePromptItem(box_id="B1", expected_label="Cell Wall", definition_hint="Wall", distractors=[]),
            PracticePromptItem(box_id="B2", expected_label="Blocked", definition_hint="No", distractors=[]),
            PracticePromptItem(box_id="B3", expected_label="Guess", definition_hint="No", distractors=[]),
            PracticePromptItem(box_id="B4", expected_label="Nucleus", definition_hint="Yes", distractors=[]),
        ],
    )
    safe = enforce_strict_status_guardrail(raw_a2, region_statuses)
    assert [s.cited_box_id for s in safe.steps] == ["B1", "B4"]
    assert [p.box_id for p in safe.practice_prompts] == ["B1", "B4"]
