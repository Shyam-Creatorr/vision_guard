from app.schemas.analysis import AuditedRegion
from app.services.demo_data import ensure_demo_image
from app.services.masking import generate_blank_label_diagram
from app.services.sm2 import compute_sm2_update


def test_blank_label_masking_excludes_unverified_regions():
    demo_path = ensure_demo_image("plant_cell")
    regions = [
        AuditedRegion(
            box_id="B1",
            label_text="Cell Wall",
            component_type="label",
            bbox_1000=[188, 25, 255, 175],
            status="VERIFIED",
            confidence=0.98,
        ),
        AuditedRegion(
            box_id="B6",
            label_text="Blurred",
            component_type="label",
            bbox_1000=[812, 804, 880, 996],
            status="UNVERIFIED",
            confidence=0.25,
            ambiguity_reason="Blurred",
        ),
    ]
    key, blanks = generate_blank_label_diagram(demo_path, regions)
    assert key.endswith("_blank.png")
    assert len(blanks) == 1
    assert blanks[0]["box_id"] == "B1"


def test_sm2_spaced_repetition_progression_and_reset():
    ef, interval, reps, _ = compute_sm2_update(2.5, 1, 0, quality=5)
    assert interval == 1 and reps == 1
    ef, interval, reps, _ = compute_sm2_update(ef, interval, reps, quality=5)
    assert interval == 6 and reps == 2
    ef, interval, reps, _ = compute_sm2_update(ef, interval, reps, quality=1)
    assert interval == 1 and reps == 0
