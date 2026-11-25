from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_csrf_token,
    hash_password,
    verify_csrf_token,
    verify_password,
)


def test_argon2_password_hash_and_verify():
    hashed = hash_password("Science123")
    assert hashed.startswith("$argon2")
    assert verify_password("Science123", hashed) is True
    assert verify_password("WrongPass1", hashed) is False


def test_jwt_and_csrf_tokens():
    tok = create_access_token("user-123", "student")
    payload = decode_access_token(tok)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "student"

    csrf = generate_csrf_token()
    assert verify_csrf_token(csrf, csrf) is True
    assert verify_csrf_token(csrf, "tampered.token") is False
