import os
from pathlib import Path
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Configure isolated test environment before importing app
_TMP_DIR = tempfile.mkdtemp(prefix="vg_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test_vg.db"
os.environ["UPLOAD_DIR"] = f"{_TMP_DIR}/uploads"
os.environ["APP_ENV"] = "development"
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-integration-tests-32b"
os.environ["CSRF_SECRET"] = "test-csrf-key-for-unit-integration-tests-32b"

from app.core.config import get_settings  # noqa: E402
get_settings.cache_clear()

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app, rate_limiter  # noqa: E402

_engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
_TestingSessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    rate_limiter.reset()
    yield


@pytest.fixture()
def db_session():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_png_bytes(width: int = 800, height: int = 600, blurry: bool = False) -> bytes:
    import cv2
    import numpy as np

    canvas = np.full((height, width, 3), 245, dtype=np.uint8)
    cv2.rectangle(canvas, (100, 100), (350, 260), (20, 40, 20), 4)
    cv2.putText(canvas, "Chloroplast", (120, 180), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (10, 10, 10), 3)
    cv2.arrowedLine(canvas, (350, 180), (500, 180), (30, 90, 160), 4)
    cv2.circle(canvas, (580, 180), 70, (40, 120, 40), 4)
    if blurry:
        canvas = cv2.GaussianBlur(canvas, (31, 31), 12)
    ok, buf = cv2.imencode(".png", canvas)
    assert ok
    return buf.tobytes()
