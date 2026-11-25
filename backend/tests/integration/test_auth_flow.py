def test_full_auth_lifecycle_and_refresh_rotation(client):
    # Signup
    res = client.post(
        "/api/v1/auth/signup",
        json={"email": "ada@science.edu", "password": "Password123", "full_name": "Ada Lovelace"},
    )
    assert res.status_code == 201
    data = res.json()
    access = data["access_token"]
    assert data["user"]["email"] == "ada@science.edu"
    assert "vg_refresh_token" in client.cookies
    csrf = client.cookies.get("vg_csrf_token")
    assert csrf

    # Onboarding PATCH
    me = client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {access}"},
        json={"grade_level": "AP Biology", "subjects": ["Biology", "Chemistry"], "onboarding_completed": True},
    )
    assert me.status_code == 200
    assert me.json()["profile"]["onboarding_completed"] is True

    # Refresh token rotation
    old_refresh = client.cookies.get("vg_refresh_token")
    ref = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert ref.status_code == 200
    new_refresh = client.cookies.get("vg_refresh_token")
    assert new_refresh != old_refresh

    # Reuse of old refresh token must fail and revoke family
    client.cookies.set("vg_refresh_token", old_refresh)
    reuse = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": client.cookies.get("vg_csrf_token")})
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "TOKEN_REUSE_DETECTED"

    # Forgot & Reset Password
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": "ada@science.edu"})
    assert forgot.status_code == 200
    dev_tok = forgot.json()["dev_reset_token"]
    reset = client.post("/api/v1/auth/reset-password", json={"token": dev_tok, "new_password": "NewPassword456"})
    assert reset.status_code == 200

    # Login with new password
    login = client.post("/api/v1/auth/login", json={"email": "ada@science.edu", "password": "NewPassword456"})
    assert login.status_code == 200

    # Logout
    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200
    assert out.json()["logged_out"] is True
