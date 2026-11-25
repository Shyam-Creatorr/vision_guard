from app.schemas.analysis import (
    Agent1VisualAudit,
    Agent2GroundedExplanation,
    AuditedRegion,
    ExplanationStep,
    PracticePromptItem,
)
from app.services.guardrail import apply_guardrail_lock, enforce_agent2_guardrails
from app.services.storage import save_validated_upload
from tests.conftest import make_png_bytes


def test_guardrail_strips_unverified_steps_and_locks_blurry_regions():
    _, _, _, _, _, blur_path = save_validated_upload(make_png_bytes(blurry=True), "blur.png")

    audit = Agent1VisualAudit(
        diagram_summary="Test diagram",
        overall_legibility="partial",
        regions=[
            AuditedRegion(
                box_id="B1",
                label_text="Hallucinated Label",
                component_type="label",
                bbox_1000=[100, 100, 300, 400],
                status="VERIFIED",
                confidence=0.95,
            ),
            AuditedRegion(
                box_id="B2",
                label_text="",
                component_type="label",
                bbox_1000=[500, 500, 700, 800],
                status="UNVERIFIED",
                confidence=0.2,
                ambiguity_reason="Smudged",
            ),
        ],
    )

    locked, verified_ids, unverified_ids = apply_guardrail_lock(
        audit, width_px=800, height_px=600, image_path=blur_path, global_blur_score=20.0
    )
    # Local CV sharpness gate forces blurry B1 into UNVERIFIED
    assert verified_ids == []
    assert set(unverified_ids) == {"B1", "B2"}

    # Even if Agent 2 attempts to cite B1 or B2 or a fabricated B99, guardrail strips them
    agent2 = Agent2GroundedExplanation(
        title="Test",
        language="en",
        steps=[
            ExplanationStep(step_number=1, heading="Bad", explanation="Guess", cited_box_id="B1"),
            ExplanationStep(step_number=2, heading="Fake", explanation="Fabricated", cited_box_id="B99"),
        ],
        practice_prompts=[
            PracticePromptItem(box_id="B2", expected_label="X", definition_hint="Y", distractors=[]),
        ],
    )
    safe = enforce_agent2_guardrails(agent2, locked, verified_ids)
    assert safe.steps == []
    assert safe.practice_prompts == []
    assert len(safe.unverified_warnings) == 2
