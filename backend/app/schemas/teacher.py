from datetime import datetime
from pydantic import BaseModel, Field


class CreateTeacherLinkRequest(BaseModel):
    job_id: str
    title: str = Field(min_length=2, max_length=160)
    instructions: str = Field(default="", max_length=1000)


class TeacherLinkResponse(BaseModel):
    id: str
    job_id: str
    share_token: str
    share_url: str
    title: str
    instructions: str
    is_active: bool
    created_at: datetime
