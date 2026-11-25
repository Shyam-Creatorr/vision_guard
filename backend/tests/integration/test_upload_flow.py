from tests.conftest import make_png_bytes


def _auth_header(client) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "uploader@science.edu", "password": "Password123", "full_name": "Uploader"},
    )
    assert res.status_code == 201
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_upload_sharp_and_blurry_diagrams(client):
    headers = _auth_header(client)

    sharp_res = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("cell.png", make_png_bytes(blurry=False), "image/png")},
    )
    assert sharp_res.status_code == 201
    sharp_data = sharp_res.json()
    assert sharp_data["quality_status"] == "pass"
    assert sharp_data["recommend_retake"] is False

    img_res = client.get(sharp_data["image_url"], headers=headers)
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/png"

    blur_res = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("blurry.png", make_png_bytes(blurry=True), "image/png")},
    )
    assert blur_res.status_code == 201
    assert blur_res.json()["quality_status"] == "fail"
    assert blur_res.json()["recommend_retake"] is True


def test_upload_rejects_fake_extension_magic_bytes(client):
    headers = _auth_header(client)
    bad_res = client.post(
        "/api/v1/uploads",
        headers=headers,
        files={"file": ("fake.jpg", b"not really a jpg file", "image/jpeg")},
    )
    assert bad_res.status_code == 400
    body = bad_res.json()
    assert body["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert "request_id" in body["error"]
