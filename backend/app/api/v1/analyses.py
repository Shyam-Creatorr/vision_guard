import asyncio
from collections.abc import AsyncGenerator
import json

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.deps import get_optional_user
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.db.models import AnalysisJob, DiagramUpload, User, UserProfile
from app.db.session import get_db
from app.schemas.analysis import (
    Agent1VisualAudit,
    Agent2GroundedExplanation,
    AnalysisJobResponse,
    CreateAnalysisRequest,
    DemoDiagramInfo,
    ExplanationStep,
    PracticePromptItem,
    RegionDecisionRequest,
)
from app.services.demo_data import DemoSlug, ensure_demo_image, list_demos
from app.services.guardrail import enforce_strict_status_guardrail
from app.services.pdf_export import render_analysis_report_pdf
from app.services.pipeline import execute_analysis_job
from app.services.storage import resolve_upload_file

router = APIRouter(prefix="/analyses", tags=["analyses"])

DEMO_USER_EMAIL = "demo-guest@visionguard.local"


def _get_or_create_demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_USER_EMAIL))
    if user:
        return user
    user = User(
        email=DEMO_USER_EMAIL,
        password_hash=hash_password("DemoGuestAccount123!"),
        role="student",
    )
    user.profile = UserProfile(full_name="Demo Explorer", onboarding_completed=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resolve_job_image_url(job: AnalysisJob) -> str | None:
    if job.demo_slug:
        return f"/api/v1/analyses/demos/{job.demo_slug}/image"
    if job.upload_id:
        return f"/api/v1/uploads/{job.upload_id}/image"
    return None


def _to_job_response(job: AnalysisJob, db: Session) -> AnalysisJobResponse:
    upload = db.get(DiagramUpload, job.upload_id) if job.upload_id else None
    res = job.result
    agent1 = Agent1VisualAudit.model_validate(res.agent1_json) if res else None
    agent2 = Agent2GroundedExplanation.model_validate(res.agent2_json) if res else None
    user_confirmed_ids = (
        [r.box_id for r in agent1.regions if r.status == "user_confirmed"]
        if agent1
        else []
    )
    unverified_ids = list(res.unverified_box_ids_json) if res else []
    return AnalysisJobResponse(
        job_id=job.id,
        status=job.status,  # type: ignore[arg-type]
        progress_pct=job.progress_pct,
        title=job.title,
        subject=job.subject,
        question=job.question,
        reference_answer=job.reference_answer,
        language=job.language,  # type: ignore[arg-type]
        demo_slug=job.demo_slug,
        image_url=_resolve_job_image_url(job),
        width_px=upload.width_px if upload else (1200 if job.demo_slug else None),
        height_px=upload.height_px if upload else (800 if job.demo_slug else None),
        blur_score=upload.blur_score if upload else (185.0 if job.demo_slug else None),
        contrast_score=upload.contrast_score if upload else (92.0 if job.demo_slug else None),
        quality_status=upload.quality_status if upload else ("pass" if job.demo_slug else None),
        is_favorite=job.is_favorite,
        used_fallback=job.used_fallback,
        limited_mode=bool(agent2 and agent2.limited_mode),
        limited_mode_notice=agent2.limited_mode_notice if agent2 else None,
        whole_image_blurry=bool(agent1 and agent1.whole_image_blurry),
        retake_recommended=bool(agent1 and agent1.retake_recommended),
        blocked_count=len(unverified_ids),
        error_code=job.error_code,
        error_message=job.error_message,
        verified_box_ids=list(res.verified_box_ids_json) if res else [],
        user_confirmed_box_ids=user_confirmed_ids,
        unverified_box_ids=unverified_ids,
        agent1=agent1,
        agent2=agent2,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/demos", response_model=list[DemoDiagramInfo])
def get_demos() -> list[DemoDiagramInfo]:
    return list_demos()


@router.get("/demos/{slug}/image")
def get_demo_image(slug: DemoSlug) -> FileResponse:
    path = ensure_demo_image(slug)
    return FileResponse(path=str(path), media_type="image/png")


@router.post("", response_model=AnalysisJobResponse, status_code=202)
def create_analysis(
    payload: CreateAnalysisRequest,
    background_tasks: BackgroundTasks,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    if not payload.upload_id and not payload.demo_slug:
        raise AppError("MISSING_SOURCE", "Provide either upload_id or demo_slug.", status_code=400)

    if payload.upload_id:
        if not user:
            raise AppError("UNAUTHORIZED", "Sign in to analyze custom uploaded diagrams.", status_code=401)
        upload = db.get(DiagramUpload, payload.upload_id)
        if not upload or upload.user_id != user.id:
            raise AppError("UPLOAD_NOT_FOUND", "Uploaded diagram not found.", status_code=404)
        owner = user
        title = (payload.title.strip() if payload.title and payload.title.strip() else "Untitled diagram")
    else:
        owner = user or _get_or_create_demo_user(db)
        title = payload.demo_slug.replace("_", " ").title()  # type: ignore[union-attr]

    job = AnalysisJob(
        user_id=owner.id,
        upload_id=payload.upload_id,
        demo_slug=payload.demo_slug,
        subject=payload.subject.strip(),
        title=title[:160],
        question=payload.question.strip(),
        reference_answer=payload.reference_answer.strip() if payload.reference_answer else None,
        language=payload.language,
        status="queued",
        progress_pct=5,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    session_factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False, expire_on_commit=False)
    background_tasks.add_task(execute_analysis_job, job.id, session_factory)

    return _to_job_response(job, db)


def _assert_job_access(job: AnalysisJob | None, user: User | None) -> AnalysisJob:
    if not job:
        raise AppError("JOB_NOT_FOUND", "Analysis job not found.", status_code=404)
    if job.demo_slug:
        return job
    if not user or job.user_id != user.id:
        raise AppError("FORBIDDEN", "You do not have access to this analysis.", status_code=403)
    return job


@router.get("/{job_id}", response_model=AnalysisJobResponse)
def get_analysis(
    job_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    return _to_job_response(job, db)


@router.get("/{job_id}/events")
async def stream_analysis_events(
    job_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    session_factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False, expire_on_commit=False)

    async def event_stream() -> AsyncGenerator[str, None]:
        last_sig = None
        for _ in range(90):
            s = session_factory()
            try:
                cur = s.get(AnalysisJob, job.id)
                if not cur:
                    break
                sig = (cur.status, cur.progress_pct)
                if sig != last_sig:
                    last_sig = sig
                    payload = {
                        "job_id": cur.id,
                        "status": cur.status,
                        "progress_pct": cur.progress_pct,
                        "error_message": cur.error_message,
                    }
                    yield f"event: stage_update\ndata: {json.dumps(payload)}\n\n"
                if cur.status in ("done", "failed"):
                    yield f"event: {cur.status}\ndata: {json.dumps({'job_id': cur.id, 'status': cur.status})}\n\n"
                    break
            finally:
                s.close()
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{job_id}/export.pdf")
def export_analysis_pdf(
    job_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> Response:
    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if job.status != "done" or not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Analysis must be completed before exporting PDF.", status_code=409)

    if job.demo_slug:
        img_path = ensure_demo_image(job.demo_slug)  # type: ignore[arg-type]
    elif job.upload_id:
        upload = db.get(DiagramUpload, job.upload_id)
        if not upload:
            raise AppError("UPLOAD_NOT_FOUND", "Diagram image missing.", status_code=404)
        img_path = resolve_upload_file(upload.normalized_key)
    else:
        raise AppError("IMAGE_NOT_FOUND", "Diagram image missing.", status_code=404)

    audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
    agent2 = Agent2GroundedExplanation.model_validate(job.result.agent2_json)
    pdf_bytes = render_analysis_report_pdf(img_path, job.title, job.question, audit, agent2)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="visionguard-report-{job.id[:8]}.pdf"'},
    )


@router.get("/{job_id}/regions/{box_id}/crop")
def get_region_crop(
    job_id: str,
    box_id: str,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> Response:
    from io import BytesIO
    from PIL import Image

    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Analysis not ready.", status_code=409)
    audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
    region = next((r for r in audit.regions if r.box_id == box_id), None)
    if not region:
        raise AppError("REGION_NOT_FOUND", "Region not found.", status_code=404)

    if job.demo_slug:
        img_path = ensure_demo_image(job.demo_slug)  # type: ignore[arg-type]
    elif job.upload_id:
        upload = db.get(DiagramUpload, job.upload_id)
        if not upload:
            raise AppError("UPLOAD_NOT_FOUND", "Upload missing.", status_code=404)
        img_path = resolve_upload_file(upload.storage_key)
    else:
        raise AppError("IMAGE_NOT_FOUND", "Image missing.", status_code=404)

    with Image.open(img_path) as im:
        w, h = im.size
        ymin, xmin, ymax, xmax = region.bbox_1000
        x1 = max(0, int(xmin * w / 1000) - 12)
        y1 = max(0, int(ymin * h / 1000) - 12)
        x2 = min(w, int(xmax * w / 1000) + 12)
        y2 = min(h, int(ymax * h / 1000) + 12)
        crop = im.crop((x1, y1, max(x1 + 4, x2), max(y1 + 4, y2)))
        buf = BytesIO()
        crop.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")


@router.post("/{job_id}/regions/{box_id}/decision", response_model=AnalysisJobResponse)
def decide_blocked_region(
    job_id: str,
    box_id: str,
    payload: RegionDecisionRequest,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> AnalysisJobResponse:
    from app.db.models import PracticeCard

    job = _assert_job_access(db.get(AnalysisJob, job_id), user)
    if not job.result:
        raise AppError("ANALYSIS_NOT_READY", "Analysis not ready.", status_code=409)

    audit = Agent1VisualAudit.model_validate(job.result.agent1_json)
    agent2 = Agent2GroundedExplanation.model_validate(job.result.agent2_json)
    region = next((r for r in audit.regions if r.box_id == box_id), None)
    if not region:
        raise AppError("REGION_NOT_FOUND", "Region not found.", status_code=404)

    if payload.action == "reject":
        region.status = "rejected"
        region.label_text = ""
        region.confirmed_by_user = False
        existing_card = db.scalar(
            select(PracticeCard).where(
                PracticeCard.user_id == job.user_id,
                PracticeCard.job_id == job.id,
                PracticeCard.box_id == box_id,
            )
        )
        if existing_card:
            db.delete(existing_card)
    else:
        chosen = (payload.label or "").strip()
        if not chosen:
            raise AppError("MISSING_LABEL", "Provide a label to confirm this region.", status_code=400)
        region.status = "user_confirmed"
        region.label_text = chosen
        region.confirmed_by_user = True
        # Ensure PracticeCard exists for user-confirmed label
        existing_card = db.scalar(
            select(PracticeCard).where(
                PracticeCard.user_id == job.user_id,
                PracticeCard.job_id == job.id,
                PracticeCard.box_id == box_id,
            )
        )
        if existing_card:
            existing_card.expected_label = chosen
            db.add(existing_card)
        else:
            db.add(
                PracticeCard(
                    user_id=job.user_id,
                    job_id=job.id,
                    box_id=box_id,
                    expected_label=chosen,
                    hint_definition=f"Confirmed by you ({chosen})",
                    distractors_json=["Nucleus", "Cytoplasm", "Membrane"],
                )
            )
        # Add/update prompt & step marked confirmed_by_user
        agent2.practice_prompts = [p for p in agent2.practice_prompts if p.box_id != box_id]
        agent2.practice_prompts.append(
            PracticePromptItem(
                box_id=box_id,
                expected_label=chosen,
                definition_hint=f"Confirmed by you for blocked region {box_id}.",
                distractors=["Nucleus", "Cytoplasm", "Membrane"],
            )
        )
        if not any(s.cited_box_id == box_id for s in agent2.steps):
            agent2.steps.append(
                ExplanationStep(
                    step_number=len(agent2.steps) + 1,
                    heading=chosen,
                    explanation=f"Confirmed by you for region {box_id} (was locked due to: {region.ambiguity_reason or 'low legibility'}).",
                    cited_box_id=box_id,
                    confidence_badge="medium",
                    confirmed_by_user=True,
                )
            )

    # Recompute verified/unverified lists and enforce strict backend guardrail
    status_map = {r.box_id: r.status for r in audit.regions}
    agent2 = enforce_strict_status_guardrail(agent2, status_map)
    agent2.unverified_warnings = [w for w in agent2.unverified_warnings if w.box_id != box_id or region.status != "user_confirmed"]

    job.result.agent1_json = audit.model_dump()
    job.result.agent2_json = agent2.model_dump()
    job.result.verified_box_ids_json = [r.box_id for r in audit.regions if r.status in ("verified", "VERIFIED")]
    job.result.unverified_box_ids_json = [r.box_id for r in audit.regions if r.status in ("unverified_blocked", "suggested", "rejected", "UNVERIFIED")]
    job.result.blank_image_key = None  # invalidate cached blank mask so quiz regenerates cleanly

    db.add(job.result)
    db.commit()
    db.refresh(job)
    return _to_job_response(job, db)
