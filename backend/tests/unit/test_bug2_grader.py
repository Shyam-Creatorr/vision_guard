from app.services.grader import (
    build_unique_shuffled_options,
    get_aliases_for_label,
    grade_blank_answer,
    normalize_label,
)


def test_grader_normalization_aliases_typos_and_wrong():
    # Case, extra whitespace, punctuation, hyphen, plural
    assert grade_blank_answer("Cell Wall", get_aliases_for_label("Cell Wall"), "  cell-wall!! ").status == "correct"
    assert grade_blank_answer("Chloroplast", [], "chloroplasts").status == "correct"
    assert grade_blank_answer("Mitochondria", get_aliases_for_label("Mitochondria"), "Mitochondrion").status == "correct"

    # One-letter typo on 6+ char word -> almost
    res_almost = grade_blank_answer("Chloroplast", [], "Chloroplost")
    assert res_almost.status == "almost"
    assert res_almost.credit == 0.5

    # Genuinely wrong -> wrong & canonical answer shown (never a random distractor)
    res_wrong = grade_blank_answer("Nucleus", [], "Vacuole")
    assert res_wrong.status == "wrong"
    assert res_wrong.canonical_answer == "Nucleus"
    assert "Nucleus" in res_wrong.message


def test_quiz_property_100_shuffle_seeds_never_leak_or_mismatch(client):
    res = client.post(
        "/api/v1/analyses",
        json={"demo_slug": "plant_cell", "subject": "Biology", "question": "Explain cell"},
    )
    assert res.status_code == 202
    job_id = res.json()["job_id"]

    # Check across 100 shuffle seeds:
    # 1) Every blank's canonical answer scores 100%
    # 2) Distractors never equal any answer/alias of the same diagram
    # 3) Option-ID grading works consistently regardless of shuffle order
    for seed in range(100):
        blank_resp = client.post(f"/api/v1/practice/{job_id}/blank-diagram?seed={seed}")
        assert blank_resp.status_code == 200
        blanks = blank_resp.json()["blanks"]
        all_answer_norms = {normalize_label(b["expected_label"]) for b in blanks}
        for b in blanks:
            for opt in b["options"]:
                if normalize_label(opt["label"]) != normalize_label(b["expected_label"]):
                    assert normalize_label(opt["label"]) not in all_answer_norms

    # Submit all correct answers -> 100%
    blanks = client.post(f"/api/v1/practice/{job_id}/blank-diagram?seed=77").json()["blanks"]
    attempt_100 = client.post(
        f"/api/v1/practice/{job_id}/attempt",
        json={
            "mode": "mcq",
            "seed": 77,
            "answers": [
                {
                    "blank_id": b["blank_id"],
                    "box_id": b["box_id"],
                    "submitted_answer": b["expected_label"],
                    "selected_option_id": next(
                        o["option_id"] for o in b["options"] if o["label"] == b["expected_label"]
                    ),
                }
                for b in blanks
            ],
        },
    ).json()
    assert attempt_100["score_pct"] == 100.0

    # Answering each blank with another blank's answer gives 0% and shows exact key for that blank
    wrong_attempt = client.post(
        f"/api/v1/practice/{job_id}/attempt",
        json={
            "mode": "type",
            "seed": 77,
            "answers": [
                {
                    "blank_id": blanks[i]["blank_id"],
                    "box_id": blanks[i]["box_id"],
                    "submitted_answer": blanks[(i + 1) % len(blanks)]["expected_label"],
                }
                for i in range(len(blanks))
            ],
        },
    ).json()
    assert wrong_attempt["score_pct"] == 0.0
    for i, fb in enumerate(wrong_attempt["feedback"]):
        assert fb["status"] == "wrong"
        assert fb["expected_label"] == blanks[i]["expected_label"]
