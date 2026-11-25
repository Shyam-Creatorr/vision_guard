from typing import Literal
from pydantic import BaseModel


class QualityReportResponse(BaseModel):
    upload_id: str
    original_filename: str
    mime_type: str
    byte_size: int
    width_px: int
    height_px: int
    blur_score: float
    contrast_score: float
    quality_status: Literal["pass", "warn", "fail"]
    quality_notes: list[str]
    recommend_retake: bool
    image_url: str
