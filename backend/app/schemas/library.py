from datetime import datetime
from pydantic import BaseModel, Field


class LibraryItem(BaseModel):
    job_id: str
    title: str
    subject: str
    status: str
    language: str
    is_favorite: bool
    verified_count: int
    unverified_count: int
    image_url: str | None
    created_at: datetime


class LibraryUpdateRequest(BaseModel):
    is_favorite: bool | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
