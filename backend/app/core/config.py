from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "VisionGuard Tutor"
    SECRET_KEY: str = Field(default="dev-insecure-secret-key-change-in-production-32bytes")
    CSRF_SECRET: str = Field(default="dev-insecure-csrf-key-change-in-production-32bytes")
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    DATABASE_URL: str = "sqlite:///./visionguard.db"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False
    GOOGLE_AUTH_ENABLED: bool = False
    GOOGLE_CLIENT_ID: str = ""

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    AI_TIMEOUT_SECONDS: int = 35

    UPLOAD_DIR: str = "./storage/uploads"
    MAX_UPLOAD_MB: int = 8
    MAX_IMAGE_DIMENSION: int = 4096

    RATE_LIMIT_PER_MINUTE: int = 120

    # Bug 1: Calibrated Region Legibility & Suggestion Thresholds
    LEGIBILITY_BLOCK_THRESHOLD: float = 0.56
    LEGIBILITY_OCR_AGREE_MIN: float = 0.60
    LEGIBILITY_MIN_CONTRAST: float = 0.22
    LEGIBILITY_MIN_SHARPNESS_NORM: float = 0.26
    LEGIBILITY_SUGGESTION_FLOOR: float = 0.20
    LEGIBILITY_TILE_GRID: int = 8

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        return Path(self.UPLOAD_DIR).resolve()

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
