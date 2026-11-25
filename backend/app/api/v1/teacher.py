from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.analyses import _to_job_response
from app.api.v1.deps import require_teacher
from app.core.exceptions import AppError
from app.core.security import generate_random_token
from app.db.models import AnalysisJob, TeacherLink, User
from app.db.session import get_db
from app.schemas.analysis import AnalysisJobResponse
from app.schemas.teacher import CreateTeacherLinkRequest, TeacherLinkResponse

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.post("/links", response_model=TeacherLinkResponse, status_code=201)
def create_teacher_link(
    payload: CreateTeacherLinkRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> TeacherLinkResponse:
    job = db.get(AnalysisJob, payload.job_id)
    if not job or (job.user_id != teacher.id and not job.demo_slug):
        raise AppError("JOB_NOT_FOUND", "Referenced analysis job not found.", status_code=404)

    token = generate_random_token(16)
    link = TeacherLink(
        teacher_id=teacher.id,
        job_id=job.id,
        share_token=token,
        title=payload.title.strip(),
        instructions=payload.instructions.strip(),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return TeacherLinkResponse(
        id=link.id,
        job_id=link.job_id,
        share_token=link.share_token,
        share_url=f"/share/{link.share_token}",
        title=link.title,
        instructions=link.instructions,
        is_active=link.is_active,
        created_at=link.created_at,
    )


@router.get("/links", response_model=list[TeacherLinkResponse])
def list_teacher_links(
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> list[TeacherLinkResponse]:
    links = db.scalars(
        select(TeacherLink)
        .where(TeacherLink.teacher_id == teacher.id)
        .order_by(TeacherLink.created_at.desc())
    ).all()
    return [
        TeacherLinkResponse(
            id=l.id,
            job_id=l.job_id,
            share_token=l.share_token,
            share_url=f"/share/{l.share_token}",
            title=l.title,
            instructions=l.instructions,
            is_active=l.is_active,
            created_at=l.created_at,
        )
        for l in links
    ]


@router.get("/share/{share_token}", response_model=dict)
def open_shared_assignment(share_token: str, db: Session = Depends(get_db)) -> dict:
    link = db.scalar(select(TeacherLink).where(TeacherLink.share_token == share_token))
    if not link or not link.is_active:
        raise AppError("SHARE_LINK_INVALID", "This teacher share link is invalid or inactive.", status_code=404)
    job = db.get(AnalysisJob, link.job_id)
    if not job:
        raise AppError("JOB_NOT_FOUND", "Shared analysis no longer exists.", status_code=404)
    analysis: AnalysisJobResponse = _to_job_response(job, db)
    return {
        "title": link.title,
        "instructions": link.instructions,
        "analysis": analysis.model_dump(),
    }
