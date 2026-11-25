from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.analyses import _resolve_job_image_url
from app.api.v1.deps import get_current_user
from app.core.exceptions import AppError
from app.db.models import AnalysisJob, User
from app.db.session import get_db
from app.schemas.library import LibraryItem, LibraryUpdateRequest

router = APIRouter(prefix="/library", tags=["library"])


@router.get("", response_model=list[LibraryItem])
def list_library(
    q: str = "",
    subject: str = "",
    favorites_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LibraryItem]:
    stmt = select(AnalysisJob).where(AnalysisJob.user_id == user.id)
    if subject.strip():
        stmt = stmt.where(AnalysisJob.subject == subject.strip())
    if favorites_only:
        stmt = stmt.where(AnalysisJob.is_favorite.is_(True))
    stmt = stmt.order_by(AnalysisJob.created_at.desc())

    jobs = db.scalars(stmt).all()
    q_norm = q.strip().lower()
    items: list[LibraryItem] = []
    for job in jobs:
        if q_norm and q_norm not in job.title.lower() and q_norm not in job.question.lower():
            continue
        res = job.result
        items.append(
            LibraryItem(
                job_id=job.id,
                title=job.title,
                subject=job.subject,
                status=job.status,
                language=job.language,
                is_favorite=job.is_favorite,
                verified_count=len(res.verified_box_ids_json) if res else 0,
                unverified_count=len(res.unverified_box_ids_json) if res else 0,
                image_url=_resolve_job_image_url(job),
                created_at=job.created_at,
            )
        )
    return items


@router.patch("/{job_id}", response_model=LibraryItem)
def update_library_item(
    job_id: str,
    payload: LibraryUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LibraryItem:
    job = db.get(AnalysisJob, job_id)
    if not job or job.user_id != user.id:
        raise AppError("JOB_NOT_FOUND", "Saved analysis not found.", status_code=404)
    if payload.is_favorite is not None:
        job.is_favorite = payload.is_favorite
    if payload.title is not None:
        job.title = payload.title.strip()
    db.add(job)
    db.commit()
    db.refresh(job)
    res = job.result
    return LibraryItem(
        job_id=job.id,
        title=job.title,
        subject=job.subject,
        status=job.status,
        language=job.language,
        is_favorite=job.is_favorite,
        verified_count=len(res.verified_box_ids_json) if res else 0,
        unverified_count=len(res.unverified_box_ids_json) if res else 0,
        image_url=_resolve_job_image_url(job),
        created_at=job.created_at,
    )


@router.delete("/{job_id}")
def delete_library_item(
    job_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    job = db.get(AnalysisJob, job_id)
    if not job or job.user_id != user.id:
        raise AppError("JOB_NOT_FOUND", "Saved analysis not found.", status_code=404)
    db.delete(job)
    db.commit()
    return {"deleted": True}
