from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user, get_optional_user
from app.core.exceptions import AppError
from app.db.models import DiagramUpload, User
from app.db.session import get_db
from app.schemas.upload import QualityReportResponse
from app.services.preprocess import analyze_and_normalize_diagram
from app.services.storage import resolve_upload_file, save_validated_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", response_model=QualityReportResponse, status_code=201)
async def upload_diagram(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QualityReportResponse:
    raw_bytes = await file.read()
    storage_key, mime_type, clean_name, width_px, height_px, abs_path = save_validated_upload(
        raw_bytes, file.filename
    )
    prep = analyze_and_normalize_diagram(abs_path)

    upload_row = DiagramUpload(
        user_id=user.id,
        storage_key=storage_key,
        normalized_key=prep.normalized_key,
        original_filename=clean_name,
        mime_type=mime_type,
        byte_size=len(raw_bytes),
        width_px=prep.width_px,
        height_px=prep.height_px,
        blur_score=prep.blur_score,
        contrast_score=prep.contrast_score,
        quality_status=prep.quality_status,
        quality_notes_json=prep.quality_notes,
        is_demo=False,
    )
    db.add(upload_row)
    db.commit()
    db.refresh(upload_row)

    return QualityReportResponse(
        upload_id=upload_row.id,
        original_filename=upload_row.original_filename,
        mime_type=upload_row.mime_type,
        byte_size=upload_row.byte_size,
        width_px=upload_row.width_px,
        height_px=upload_row.height_px,
        blur_score=upload_row.blur_score,
        contrast_score=upload_row.contrast_score,
        quality_status=upload_row.quality_status,  # type: ignore[arg-type]
        quality_notes=list(upload_row.quality_notes_json or []),
        recommend_retake=prep.recommend_retake,
        image_url=f"/api/v1/uploads/{upload_row.id}/image",
    )


@router.get("/{upload_id}/image")
def get_uploaded_image(
    upload_id: str,
    normalized: bool = False,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    upload_row = db.get(DiagramUpload, upload_id)
    if not upload_row:
        raise AppError("UPLOAD_NOT_FOUND", "Diagram upload not found.", status_code=404)
    if not upload_row.is_demo and (not user or upload_row.user_id != user.id):
        raise AppError("FORBIDDEN", "You do not have access to this diagram.", status_code=403)

    key = upload_row.normalized_key if normalized else upload_row.storage_key
    file_path = resolve_upload_file(key)
    return FileResponse(path=str(file_path), media_type="image/png")
