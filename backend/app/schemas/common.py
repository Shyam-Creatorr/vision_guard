from typing import Any
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
