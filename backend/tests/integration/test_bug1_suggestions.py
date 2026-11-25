from pathlib import Path

FIX_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "degraded"


def _signup_headers(client, email="bug1_e2e@science.edu"):
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123", "full_name": "Bug1 Tester"},
    )
    assert res.status_code == 201
    # Cookie vg_access_token is also set for <img>/canvas requests
    assert "vg_access_token" in client.cookies
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_degraded_upload_blocks_blurry_region_and_allows_user_confirm_flow(client):
    headers = _signup_headers(client)
    img_bytes = (FIX_DIR / "01_plant_cell_gaussian_blur.png").read_bytes()

    up = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("01_plant_cell_gaussian_blur.png", img_bytes, "image/png")},
    )
    assert up.status_code == 201
    upload_data = up.json()

    # Cookie-only image fetch (simulating browser <img> / <canvas> without Bearer header) must return 200, NOT 403!
    img_resp = client.get(upload_data["image_url"])
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"] == "image/png"

    create = client.post(
        "/api/v1/analyses",
        headers=headers,
        json={
            "upload_id": upload_data["upload_id"],
            "subject": "Biology",
            "question": "Identify verified labels and block blurred ones.",
        },
    )
    assert create.status_code == 202
    job_id = create.json()["job_id"]

    job = client.get(f"/api/v1/analyses/{job_id}", headers=headers).json()
    assert job["status"] == "done"
    assert job["title"] == "Untitled diagram"
    assert job["limited_mode"] is True
    assert job["blocked_count"] >= 1
    assert job["agent2"]["steps"] == []  # Limited Mode produces zero fake explanations

    regions = job["agent1"]["regions"]
    labels = [r["label_text"] for r in regions]
    assert all("Detected Structure" not in lbl for lbl in labels)

    blocked = [r for r in regions if r["status"] in ("unverified_blocked", "suggested")]
    assert len(blocked) >= 1
    target_box = blocked[0]["box_id"]

    # Crop endpoint works for side-panel preview
    crop = client.get(f"/api/v1/analyses/{job_id}/regions/{target_box}/crop")
    assert crop.status_code == 200
    assert crop.headers["content-type"] == "image/png"

    # Rejecting keeps it excluded from quiz
    rej = client.post(
        f"/api/v1/analyses/{job_id}/regions/{target_box}/decision",
        headers=headers,
        json={"action": "reject"},
    )
    assert rej.status_code == 200
    blank_before = client.post(f"/api/v1/practice/{job_id}/blank-diagram", headers=headers).json()
    assert all(b["box_id"] != target_box for b in blank_before["blanks"])

    # Accepting / confirming custom label promotes to user_confirmed & includes in quiz
    acc = client.post(
        f"/api/v1/analyses/{job_id}/regions/{target_box}/decision",
        headers=headers,
        json={"action": "custom", "label": "Golgi Apparatus"},
    )
    assert acc.status_code == 200
    acc_body = acc.json()
    assert target_box in acc_body["user_confirmed_box_ids"]
    # Never counted as image-verified
    assert target_box not in acc_body["verified_box_ids"]

    blank_after = client.post(f"/api/v1/practice/{job_id}/blank-diagram", headers=headers).json()
    assert any(b["box_id"] == target_box and b["expected_label"] == "Golgi Apparatus" for b in blank_after["blanks"])


def test_whole_image_blur_recommends_retake_in_limited_mode(client):
    headers = _signup_headers(client, email="fullblur@science.edu")
    img_bytes = (FIX_DIR / "08_atom_shells_full_blur.png").read_bytes()

    up = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("blurry_atom.png", img_bytes, "image/png")},
    )
    assert up.status_code == 201
    assert up.json()["recommend_retake"] is True

    create = client.post(
        "/api/v1/analyses",
        headers=headers,
        json={"upload_id": up.json()["upload_id"], "subject": "Physics", "question": "Check blur"},
    )
    job = client.get(f"/api/v1/analyses/{create.json()['job_id']}", headers=headers).json()
    assert job["limited_mode"] is True
    assert job["whole_image_blurry"] is True
    assert job["retake_recommended"] is True
