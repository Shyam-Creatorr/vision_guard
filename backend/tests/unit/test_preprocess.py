from pathlib import Path
from app.core.exceptions import AppError
from app.services.preprocess import analyze_and_normalize_diagram
from app.services.storage import detect_mime_from_magic_bytes, sanitize_filename, save_validated_upload
from tests.conftest import make_png_bytes
import pytest


def test_magic_bytes_and_filename_sanitization():
    png = make_png_bytes()
    assert detect_mime_from_magic_bytes(png) == "image/png"
    assert detect_mime_from_magic_bytes(b"not-an-image-payload-12345") is None
    assert sanitize_filename("../../etc/passwd?bad.png") == "passwd_bad.png"


def test_save_validated_upload_rejects_spoofed_bytes():
    with pytest.raises(AppError) as exc:
        save_validated_upload(b"#!/bin/sh\necho fake png", "evil.png")
    assert exc.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_preprocess_distinguishes_sharp_vs_blurry():
    sharp_bytes = make_png_bytes(800, 600, blurry=False)
    blurry_bytes = make_png_bytes(800, 600, blurry=True)

    _, _, _, _, _, sharp_path = save_validated_upload(sharp_bytes, "sharp.png")
    _, _, _, _, _, blur_path = save_validated_upload(blurry_bytes, "blurry.png")

    sharp_rep = analyze_and_normalize_diagram(sharp_path)
    blur_rep = analyze_and_normalize_diagram(blur_path)

    assert sharp_rep.blur_score > blur_rep.blur_score * 5
    assert sharp_rep.quality_status == "pass"
    assert blur_rep.quality_status == "fail"
    assert blur_rep.recommend_retake is True
    assert Path(sharp_path).exists()
