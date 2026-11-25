from tests.conftest import make_png_bytes


def _signup_and_headers(client, role="student", email="learner@science.edu"):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123", "full_name": "Marie Curie", "role": role},
    )
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_demo_mode_analysis_practice_export_and_library(client):
    headers = _signup_and_headers(client, role="teacher", email="prof@science.edu")

    demos = client.get("/api/v1/analyses/demos")
    assert demos.status_code == 200
    assert len(demos.json()) == 3

    # Start Plant Cell demo analysis with reference answer
    create = client.post(
        "/api/v1/analyses",
        headers=headers,
        json={
            "demo_slug": "plant_cell",
            "subject": "Biology",
            "question": "Explain the plant cell organelles",
            "reference_answer": "Cell wall provides support and chloroplast runs photosynthesis.",
            "language": "en",
        },
    )
    assert create.status_code == 202
    job_id = create.json()["job_id"]

    job = client.get(f"/api/v1/analyses/{job_id}", headers=headers)
    assert job.status_code == 200
    body = job.json()
    assert body["status"] == "done"
    assert "B6" in body["unverified_box_ids"]
    assert all(step["cited_box_id"] in body["verified_box_ids"] for step in body["agent2"]["steps"])
    assert body["agent2"]["rubric"]["score_out_of_10"] > 0

    # Generate Blank-Label Duplicate & verify UNVERIFIED B6 is absent
    blank = client.post(f"/api/v1/practice/{job_id}/blank-diagram", headers=headers)
    assert blank.status_code == 200
    blank_data = blank.json()
    assert all(b["box_id"] != "B6" for b in blank_data["blanks"])

    # Attempting to quiz on UNVERIFIED B6 must be rejected
    bad_attempt = client.post(
        f"/api/v1/practice/{job_id}/attempt",
        headers=headers,
        json={"mode": "type", "duration_sec": 10, "answers": [{"box_id": "B6", "submitted_answer": "Golgi"}]},
    )
    assert bad_attempt.status_code == 400
    assert bad_attempt.json()["error"]["code"] == "UNVERIFIED_PRACTICE_BLOCKED"

    # Valid Practice Attempt
    good_attempt = client.post(
        f"/api/v1/practice/{job_id}/attempt",
        headers=headers,
        json={
            "mode": "type",
            "duration_sec": 24,
            "answers": [
                {"box_id": "B1", "submitted_answer": "Cell Wall"},
                {"box_id": "B2", "submitted_answer": "Chloroplast"},
            ],
        },
    )
    assert good_attempt.status_code == 200
    assert good_attempt.json()["score_pct"] == 100.0

    # Exports (PDF report + PNG/PDF worksheet)
    assert client.get(f"/api/v1/analyses/{job_id}/export.pdf", headers=headers).headers["content-type"] == "application/pdf"
    assert client.get(f"/api/v1/practice/{job_id}/worksheet.png", headers=headers).headers["content-type"] == "image/png"
    assert client.get(f"/api/v1/practice/{job_id}/worksheet.pdf", headers=headers).headers["content-type"] == "application/pdf"

    # Teacher link & share view
    link = client.post(
        "/api/v1/teacher/links",
        headers=headers,
        json={"job_id": job_id, "title": "Bio 101 Cell Quiz", "instructions": "Label all verified parts."},
    )
    assert link.status_code == 201
    share = client.get(f"/api/v1/teacher/share/{link.json()['share_token']}")
    assert share.status_code == 200
    assert share.json()["title"] == "Bio 101 Cell Quiz"

    # Library search & favorite
    lib = client.get("/api/v1/library?q=Plant", headers=headers)
    assert lib.status_code == 200 and len(lib.json()) == 1
    fav = client.patch(f"/api/v1/library/{job_id}", headers=headers, json={"is_favorite": True})
    assert fav.status_code == 200 and fav.json()["is_favorite"] is True


def test_blurry_upload_produces_unverified_regions_and_blocks_explanation(client):
    headers = _signup_and_headers(client, email="blur@science.edu")
    up = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("blurry.png", make_png_bytes(blurry=True), "image/png")},
    )
    assert up.status_code == 201
    upload_id = up.json()["upload_id"]

    job = client.post(
        "/api/v1/analyses",
        headers=headers,
        json={"upload_id": upload_id, "subject": "Biology", "question": "What does this show?"},
    )
    assert job.status_code == 202
    done = client.get(f"/api/v1/analyses/{job.json()['job_id']}", headers=headers).json()
    assert done["status"] == "done"
    assert len(done["unverified_box_ids"]) >= 1
    assert len(done["agent2"]["unverified_warnings"]) >= 1
    assert done["agent2"]["steps"] == []
