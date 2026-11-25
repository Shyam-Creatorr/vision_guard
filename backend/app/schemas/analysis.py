from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

RegionStatus = Literal[
    "verified",
    "unverified_blocked",
    "suggested",
    "user_confirmed",
    "rejected",
    "VERIFIED",
    "UNVERIFIED",
]


class CandidateSuggestion(BaseModel):
    label: str
    probability_pct: float = Field(ge=0.0, le=100.0)
    source: str = "ocr+elimination"


class AuditedRegion(BaseModel):
    box_id: str = Field(min_length=1, max_length=24)
    label_text: str = Field(default="", max_length=160)
    component_type: Literal["label", "structure", "arrow", "region"] = "label"
    bbox_1000: list[int] = Field(min_length=4, max_length=4)  # [ymin, xmin, ymax, xmax]
    bbox_px: list[int] | None = None  # [x1, y1, x2, y2] in original pixels
    status: RegionStatus
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguity_reason: str | None = Field(default=None, max_length=240)
    legibility_score: float | None = None
    local_sharpness: float | None = None
    local_contrast: float | None = None
    ocr_text: str | None = None
    ocr_confidence: float | None = None
    partially_blurry: bool = False
    suggestions: list[CandidateSuggestion] = Field(default_factory=list)
    no_reliable_suggestion: bool = False
    confirmed_by_user: bool = False


class DiagramConnection(BaseModel):
    from_box_id: str
    to_box_id: str
    relation: str = Field(max_length=160)
    status: Literal["VERIFIED", "UNVERIFIED", "verified", "unverified_blocked"] = "verified"


class Agent1VisualAudit(BaseModel):
    diagram_summary: str = Field(max_length=600)
    overall_legibility: Literal["clear", "partial", "poor"]
    whole_image_blurry: bool = False
    retake_recommended: bool = False
    regions: list[AuditedRegion] = Field(default_factory=list)
    connections: list[DiagramConnection] = Field(default_factory=list)


class ExplanationStep(BaseModel):
    step_number: int = Field(ge=1, le=20)
    heading: str = Field(min_length=1, max_length=160)
    explanation: str = Field(min_length=1, max_length=1000)
    cited_box_id: str = Field(min_length=1, max_length=24)
    confidence_badge: Literal["high", "medium"] = "high"
    confirmed_by_user: bool = False


class RubricComparison(BaseModel):
    score_out_of_10: float = Field(ge=0.0, le=10.0)
    matched_concepts: list[str] = Field(default_factory=list)
    missing_details: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    feedback_summary: str = Field(max_length=800)


class UnverifiedWarning(BaseModel):
    box_id: str
    region_hint: str
    reason: str
    warning_message: str


class PracticePromptItem(BaseModel):
    box_id: str
    expected_label: str
    definition_hint: str
    distractors: list[str] = Field(default_factory=list, max_length=4)


class Agent2GroundedExplanation(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    language: Literal["en", "hi", "kn"] = "en"
    limited_mode: bool = False
    limited_mode_notice: str | None = None
    steps: list[ExplanationStep] = Field(default_factory=list)
    rubric: RubricComparison | None = None
    unverified_warnings: list[UnverifiedWarning] = Field(default_factory=list)
    practice_prompts: list[PracticePromptItem] = Field(default_factory=list)


class CreateAnalysisRequest(BaseModel):
    upload_id: str | None = None
    demo_slug: Literal["plant_cell", "human_heart", "water_cycle"] | None = None
    subject: str = Field(default="Biology", min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=160)
    question: str = Field(min_length=3, max_length=600)
    reference_answer: str | None = Field(default=None, max_length=2000)
    language: Literal["en", "hi", "kn"] = "en"


class RegionDecisionRequest(BaseModel):
    action: Literal["accept", "reject", "custom"]
    label: str | None = Field(default=None, max_length=120)


class DemoDiagramInfo(BaseModel):
    slug: Literal["plant_cell", "human_heart", "water_cycle"]
    title: str
    subject: str
    default_question: str
    default_reference: str
    verified_count: int
    unverified_count: int
    image_url: str


class AnalysisJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "preprocessing", "auditing", "guardrail", "tutoring", "done", "failed"]
    progress_pct: int
    title: str
    subject: str
    question: str
    reference_answer: str | None
    language: Literal["en", "hi", "kn"]
    demo_slug: str | None
    image_url: str | None
    width_px: int | None
    height_px: int | None
    blur_score: float | None
    contrast_score: float | None
    quality_status: str | None
    is_favorite: bool
    used_fallback: bool
    limited_mode: bool = False
    limited_mode_notice: str | None = None
    whole_image_blurry: bool = False
    retake_recommended: bool = False
    blocked_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    verified_box_ids: list[str] = Field(default_factory=list)
    user_confirmed_box_ids: list[str] = Field(default_factory=list)
    unverified_box_ids: list[str] = Field(default_factory=list)
    agent1: Agent1VisualAudit | None = None
    agent2: Agent2GroundedExplanation | None = None
    created_at: datetime
    completed_at: datetime | None = None
