from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class QuizOptionItem(BaseModel):
    option_id: str
    label: str


class BlankItem(BaseModel):
    blank_id: str
    blank_number: int
    box_id: str
    expected_label: str
    accepted_aliases: list[str] = Field(default_factory=list)
    first_letter_hint: str
    definition_hint: str
    options: list[QuizOptionItem] = Field(default_factory=list)
    distractors: list[str] = Field(default_factory=list)
    bbox_1000: list[int]
    bbox_px: list[int] | None = None


class BlankDiagramResponse(BaseModel):
    job_id: str
    title: str
    seed: int
    original_image_url: str
    blank_image_url: str
    blanks: list[BlankItem]
    word_bank: list[QuizOptionItem] = Field(default_factory=list)
    unverified_locked_count: int


class AnswerSubmission(BaseModel):
    blank_id: str | None = None
    box_id: str
    submitted_answer: str = Field(default="", max_length=160)
    selected_option_id: str | None = None
    used_hint: bool = False


class SubmitPracticeRequest(BaseModel):
    mode: Literal["type", "drag", "mcq", "timed"]
    seed: int = 42
    duration_sec: int = Field(default=30, ge=0, le=3600)
    answers: list[AnswerSubmission] = Field(min_length=1)


class AnswerFeedback(BaseModel):
    blank_id: str
    box_id: str
    expected_label: str
    submitted_answer: str
    normalized_input: str
    status: Literal["correct", "almost", "wrong"]
    explanation: str
    next_review_days: int


class SubmitPracticeResponse(BaseModel):
    score_pct: float
    correct_count: int
    total_count: int
    xp_awarded: int
    newly_awarded_badges: list[str]
    feedback: list[AnswerFeedback]


class DueCardItem(BaseModel):
    card_id: str
    job_id: str
    job_title: str
    box_id: str
    expected_label: str
    hint_definition: str
    distractors: list[str]
    interval_days: int
    repetitions: int
    next_review_at: datetime
