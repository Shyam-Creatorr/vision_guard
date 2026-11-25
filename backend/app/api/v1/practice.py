import random

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.analyses import _assert_job_access, _resolve_job_image_url
from app.api.v1.deps import get_current_user, get_optional_user
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.db.models import AnalysisJob, DiagramUpload, PracticeAttempt, PracticeCard, User
from app.db.session import get_db
from app.schemas.analysis import Agent1VisualAudit, Agent2GroundedExplanation
from app.schemas.practice import (
    AnswerFeedback,
    BlankDiagramResponse,
    BlankItem,
    DueCardItem,
    QuizOptionItem,
    SubmitPracticeRequest,
    SubmitPracticeResponse,
)
from app.services.demo_data import ensure_demo_image
from app.services.gamification import award_xp_and_badges
from app.services.grader import (
    build_unique_shuffled_options,
    get_aliases_for_label,
    grade_blank_answer,
    normalize_label,
)
from app.services.masking import generate_blank_label_diagram, render_worksheet_pdf
from app.services.sm2 import compute_sm2_update
from app.services.storage import resolve_upload_file

router = APIRouter(prefix="/practice", tags=["practice"])
logger = get_logger(__name__)


def _get_source_image_path(job: AnalysisJob, db: Session):
    if job.demo_slug:
        return ensure_demo_image(job.demo_slug)  # type: ignore[arg-type]
    if job.upload_id:
        upload = db.get(DiagramUpload, job.upload_id)
        if upload:
            return resolve_upload_file(upload.normalized_key)
    raise AppError("IMAGE_NOT_FOUND", "Source diagram image was not found.", status_code=404)


def _all_diagram_answer_norms(raw_blanks: list[dict]) -> set[str]:
    norms: set[str] = set()
    for item in raw_blanks:
        lbl = item["expected_label"]
        norms.add(normalize_label(lbl))
        for al in get_aliases_for_label(lbl):
            norms.add(normalize_label(al))
    return norms


@router.post("/{job_id}/blank-diagram", response_model=BlankDiagramResponse)
def get_or_generate_blank_diagram(
    job_id: str,
    seed: int = 42,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> BlankDiagramResponse:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if job.status != "done" or not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Complete the analysis before generating Practice Mode.", status_code=409)

    audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
    agent2 = Agent2GroundedExplanation.model_validate(job.result.agent2_json)
    source_path = _get_source_image_path(job, db)

    blank_key, raw_blanks = generate_blank_label_diagram(source_path, audit.regions)
    job.result.blank_image_key = blank_key
    db.add(job.result)
    db.commit()

    prompt_map = {p.box_id: p for p in agent2.practice_prompts}
    all_norms = _all_diagram_answer_norms(raw_blanks)
    blanks: list[BlankItem] = []
    word_bank: list[QuizOptionItem] = []

    for item in raw_blanks:
        box_id = item["box_id"]
        blank_id = f"{job.id}:{box_id}"
        label = item["expected_label"]
        aliases = get_aliases_for_label(label)
        p = prompt_map.get(box_id)
        first_hint = f"Starts with '{label[0]}' ({len(label)} chars)" if label else "Verified label"

        opts = build_unique_shuffled_options(
            blank_id=blank_id,
            canonical_answer=label,
            raw_distractors=p.distractors if p else [],
            all_diagram_answers_and_aliases_norm=all_norms,
            seed=seed,
        )
        # Canonical option_id for drag-and-drop word bank
        ans_opt = next((o for o in opts if normalize_label(o.label) == normalize_label(label)), opts[0])
        word_bank.append(QuizOptionItem(option_id=ans_opt.option_id, label=label))

        blanks.append(
            BlankItem(
                blank_id=blank_id,
                blank_number=item["blank_number"],
                box_id=box_id,
                expected_label=label,
                accepted_aliases=aliases,
                first_letter_hint=first_hint,
                definition_hint=p.definition_hint if p else f"Verified diagram region {box_id}",
                options=[QuizOptionItem(option_id=o.option_id, label=o.label) for o in opts],
                distractors=[o.label for o in opts if o.label != label],
                bbox_1000=item["bbox_1000"],
                bbox_px=item["bbox_px"],
            )
        )

    random.Random(seed).shuffle(word_bank)

    return BlankDiagramResponse(
        job_id=job.id,
        title=job.title,
        seed=seed,
        original_image_url=_resolve_job_image_url(job) or "",
        blank_image_url=f"/api/v1/practice/{job.id}/blank-image",
        blanks=blanks,
        word_bank=word_bank,
        unverified_locked_count=len(job.result.unverified_box_ids_json or []),
    )


@router.get("/{job_id}/blank-image")
def get_blank_diagram_image(
    job_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if not job.result or not job.result.blank_image_key:
        raise AppError("BLANK_NOT_GENERATED", "Generate the blank diagram first.", status_code=404)
    path = resolve_upload_file(job.result.blank_image_key)
    return FileResponse(path=str(path), media_type="image/png")


@router.post("/{job_id}/attempt", response_model=SubmitPracticeResponse)
def submit_practice_attempt(
    job_id: str,
    payload: SubmitPracticeRequest,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> SubmitPracticeResponse:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if job.status != "done" or not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Analysis is not completed.", status_code=409)

    audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
    agent2 = Agent2GroundedExplanation.model_validate(job.result.agent2_json)
    allowed_ids = {
        r.box_id for r in audit.regions if r.status in ("verified", "user_confirmed", "VERIFIED")
    }

    region_map = {r.box_id: r for r in audit.regions if r.box_id in allowed_ids}
    hint_map = {p.box_id: p.definition_hint for p in agent2.practice_prompts}
    prompt_map = {p.box_id: p for p in agent2.practice_prompts}

    # Build option_id lookup across all verified blanks so option_id matching is always ID-based
    all_norms = {normalize_label(r.label_text) for r in region_map.values() if r.label_text}
    option_lookup: dict[str, str] = {}
    for bid, reg in region_map.items():
        if not reg.label_text.strip():
            continue
        b_id = f"{job.id}:{bid}"
        p = prompt_map.get(bid)
        opts = build_unique_shuffled_options(
            blank_id=b_id,
            canonical_answer=reg.label_text.strip(),
            raw_distractors=p.distractors if p else [],
            all_diagram_answers_and_aliases_norm=all_norms,
            seed=payload.seed,
        )
        for o in opts:
            option_lookup[o.option_id] = o.label

    feedback: list[AnswerFeedback] = []
    credit_sum = 0.0
    correct_count = 0

    for ans in payload.answers:
        if ans.box_id not in allowed_ids or ans.box_id not in region_map:
            raise AppError(
                "UNVERIFIED_PRACTICE_BLOCKED",
                f"Box {ans.box_id} is not verified or user-confirmed and cannot be quizzed.",
                status_code=400,
            )
        blank_id = ans.blank_id or f"{job.id}:{ans.box_id}"
        canonical = region_map[ans.box_id].label_text.strip()
        aliases = get_aliases_for_label(canonical)

        outcome = grade_blank_answer(
            canonical_answer=canonical,
            accepted_aliases=aliases,
            submitted_answer=ans.submitted_answer,
            selected_option_id=ans.selected_option_id,
            option_lookup=option_lookup if ans.selected_option_id else None,
        )

        logger.info(
            "Graded practice blank",
            extra={
                "extra_data": {
                    "blank_id": blank_id,
                    "box_id": ans.box_id,
                    "answer_key": canonical,
                    "submitted": ans.submitted_answer,
                    "normalized": outcome.normalized_input,
                    "result": outcome.status,
                }
            },
        )

        credit_sum += outcome.credit
        if outcome.status == "correct":
            correct_count += 1
            quality = 4 if ans.used_hint else 5
        elif outcome.status == "almost":
            quality = 3
        else:
            quality = 1

        next_days = 1
        if user:
            card = db.scalar(
                select(PracticeCard).where(
                    PracticeCard.user_id == user.id,
                    PracticeCard.job_id == job.id,
                    PracticeCard.box_id == ans.box_id,
                )
            )
            if card:
                ef, interval, reps, next_dt = compute_sm2_update(
                    card.easiness_factor, card.interval_days, card.repetitions, quality
                )
                card.easiness_factor = ef
                card.interval_days = interval
                card.repetitions = reps
                card.next_review_at = next_dt
                card.last_quality = quality
                db.add(card)
                next_days = interval

        expl = hint_map.get(ans.box_id, f"This verified region represents {canonical}.")
        feedback.append(
            AnswerFeedback(
                blank_id=blank_id,
                box_id=ans.box_id,
                expected_label=canonical,
                submitted_answer=ans.submitted_answer,
                normalized_input=outcome.normalized_input,
                status=outcome.status,  # type: ignore[arg-type]
                explanation=f"{outcome.message} {expl}",
                next_review_days=next_days,
            )
        )

    total = len(payload.answers)
    score_pct = round((credit_sum / max(1, total)) * 100.0, 1)
    xp_awarded = 15 + int(round(credit_sum * 12))
    new_badges: list[str] = []

    if user:
        db.add(
            PracticeAttempt(
                user_id=user.id,
                job_id=job.id,
                mode=payload.mode,
                score_pct=score_pct,
                xp_awarded=xp_awarded,
                duration_sec=payload.duration_sec,
            )
        )
        badges = ["quiz_ace"] if score_pct >= 80.0 else []
        new_badges = award_xp_and_badges(db, user, xp_gain=xp_awarded, badge_codes=badges)
        db.commit()

    return SubmitPracticeResponse(
        score_pct=score_pct,
        correct_count=correct_count,
        total_count=total,
        xp_awarded=xp_awarded,
        newly_awarded_badges=new_badges,
        feedback=feedback,
    )


@router.get("/due", response_model=list[DueCardItem])
def get_due_review_cards(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DueCardItem]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    cards = db.scalars(
        select(PracticeCard)
        .where(PracticeCard.user_id == user.id, PracticeCard.next_review_at <= now)
        .order_by(PracticeCard.next_review_at.asc())
        .limit(25)
    ).all()

    out: list[DueCardItem] = []
    for card in cards:
        job = db.get(AnalysisJob, card.job_id)
        out.append(
            DueCardItem(
                card_id=card.id,
                job_id=card.job_id,
                job_title=job.title if job else "Diagram Review",
                box_id=card.box_id,
                expected_label=card.expected_label,
                hint_definition=card.hint_definition,
                distractors=list(card.distractors_json or []),
                interval_days=card.interval_days,
                repetitions=card.repetitions,
                next_review_at=card.next_review_at,
            )
        )
    return out


@router.get("/{job_id}/worksheet.png")
def download_worksheet_png(
    job_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Analysis not ready.", status_code=409)
    if not job.result.blank_image_key:
        audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
        blank_key, _ = generate_blank_label_diagram(_get_source_image_path(job, db), audit.regions)
        job.result.blank_image_key = blank_key
        db.add(job.result)
        db.commit()
    path = resolve_upload_file(job.result.blank_image_key)
    return FileResponse(
        path=str(path),
        media_type="image/png",
        filename=f"visionguard-worksheet-{job.id[:8]}.png",
    )


@router.get("/{job_id}/worksheet.pdf")
def download_worksheet_pdf(
    job_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> Response:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Analysis not ready.", status_code=409)
    audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
    if not job.result.blank_image_key:
        blank_key, _ = generate_blank_label_diagram(_get_source_image_path(job, db), audit.regions)
        job.result.blank_image_key = blank_key
        db.add(job.result)
        db.commit()
    path = resolve_upload_file(job.result.blank_image_key)
    pdf_bytes = render_worksheet_pdf(
        path,
        job.title,
        len(job.result.verified_box_ids_json or []),
        len(job.result.unverified_box_ids_json or []),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="visionguard-worksheet-{job.id[:8]}.pdf"'},
    )
