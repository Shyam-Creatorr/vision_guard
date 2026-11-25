from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.db.models import AnalysisJob, AnalysisResult, DiagramUpload, PracticeCard, User
from app.services.demo_data import build_demo_pipeline_outputs, build_offline_upload_audit
from app.services.gamification import award_xp_and_badges
from app.services.gemini_client import GeminiDiagramClient, ModelUnavailableError
from app.services.guardrail import apply_guardrail_lock, enforce_agent2_guardrails
from app.services.storage import resolve_upload_file

logger = get_logger(__name__)


def _update_stage(db: Session, job: AnalysisJob, status: str, pct: int) -> None:
    job.status = status
    job.progress_pct = pct
    db.add(job)
    db.commit()


def execute_analysis_job(
    job_id: str,
    session_factory: sessionmaker,
    gemini_client_factory: Callable[[], GeminiDiagramClient] = GeminiDiagramClient,
) -> None:
    """
    Runs the full two-stage Guardrailed AI pipeline for an AnalysisJob.
    Never fails silently: writes explicit error_code/message on fatal failures,
    and falls back cleanly to deterministic CV/demo analysis if model is unavailable.
    """
    db: Session = session_factory()
    try:
        job = db.get(AnalysisJob, job_id)
        if not job:
            return

        _update_stage(db, job, "preprocessing", 20)

        used_fallback = False
        width_px = 1200
        height_px = 800
        blur_score = 180.0
        image_path: Path | None = None

        if job.demo_slug:
            raw_audit, raw_agent2, image_path = build_demo_pipeline_outputs(
                job.demo_slug,  # type: ignore[arg-type]
                job.reference_answer,
                job.language,
            )
            with Image.open(image_path) as im:
                width_px, height_px = im.size
            _update_stage(db, job, "auditing", 48)
            _update_stage(db, job, "guardrail", 70)
            locked_audit, verified_ids, unverified_ids = apply_guardrail_lock(
                raw_audit,
                width_px=width_px,
                height_px=height_px,
                image_path=None,  # demo boxes already carry calibrated demo blur/status
            )
            _update_stage(db, job, "tutoring", 88)
            safe_agent2 = enforce_agent2_guardrails(raw_agent2, locked_audit, verified_ids)
        else:
            if not job.upload_id:
                raise ValueError("Analysis job has neither demo_slug nor upload_id.")
            upload = db.get(DiagramUpload, job.upload_id)
            if not upload:
                raise ValueError("Associated upload record not found.")
            # Use EXIF-oriented original PNG for legibility/blur checks so CLAHE doesn't mask blur
            image_path = resolve_upload_file(upload.storage_key)
            width_px = upload.width_px
            height_px = upload.height_px
            blur_score = upload.blur_score

            _update_stage(db, job, "auditing", 45)
            client = gemini_client_factory()
            try:
                raw_audit = client.run_visual_audit(image_path)
            except ModelUnavailableError as exc:
                logger.info("Using deterministic CV fallback for Visual Audit", extra={"extra_data": {"reason": str(exc)}})
                used_fallback = True
                raw_audit, fallback_agent2 = build_offline_upload_audit(
                    image_path=image_path,
                    blur_score=blur_score,
                    question=job.question,
                    reference_answer=job.reference_answer,
                    language=job.language,
                    title=job.title,
                )

            _update_stage(db, job, "guardrail", 68)
            locked_audit, verified_ids, unverified_ids = apply_guardrail_lock(
                raw_audit,
                width_px=width_px,
                height_px=height_px,
                image_path=image_path,
                global_blur_score=blur_score,
                subject=job.subject,
                topic_hint=job.title,
            )

            _update_stage(db, job, "tutoring", 86)
            if not used_fallback:
                try:
                    raw_agent2 = client.run_grounded_tutor(
                        audit=locked_audit,
                        verified_ids=verified_ids,
                        question=job.question,
                        reference_answer=job.reference_answer,
                        language=job.language,
                    )
                except ModelUnavailableError:
                    used_fallback = True
                    _, raw_agent2 = build_offline_upload_audit(
                        image_path=image_path,
                        blur_score=blur_score,
                        question=job.question,
                        reference_answer=job.reference_answer,
                        language=job.language,
                        title=job.title,
                    )
            else:
                raw_agent2 = fallback_agent2

            safe_agent2 = enforce_agent2_guardrails(raw_agent2, locked_audit, verified_ids)

        # Persist result & create SM-2 PracticeCards ONLY for verified regions
        existing_res = db.get(AnalysisResult, job.id)
        if existing_res:
            db.delete(existing_res)
            db.flush()

        db.add(
            AnalysisResult(
                job_id=job.id,
                agent1_json=locked_audit.model_dump(),
                verified_box_ids_json=verified_ids,
                unverified_box_ids_json=unverified_ids,
                agent2_json=safe_agent2.model_dump(),
                schema_version="1.0",
            )
        )

        prompt_map = {p.box_id: p for p in safe_agent2.practice_prompts}
        verified_set = set(verified_ids)
        for region in locked_audit.regions:
            if region.box_id not in verified_set or not region.label_text.strip():
                continue
            p_item = prompt_map.get(region.box_id)
            db.add(
                PracticeCard(
                    user_id=job.user_id,
                    job_id=job.id,
                    box_id=region.box_id,
                    expected_label=region.label_text,
                    hint_definition=p_item.definition_hint if p_item else f"Verified region {region.box_id}",
                    distractors_json=p_item.distractors if p_item else ["Nucleus", "Membrane", "Cytoplasm"],
                )
            )

        user = db.get(User, job.user_id)
        if user and user.profile:
            badges = ["first_audit"]
            if unverified_ids:
                badges.append("sharp_eye")
            if job.language in ("hi", "kn"):
                badges.append("multilingual_explorer")
            award_xp_and_badges(db, user, xp_gain=35, badge_codes=badges, count_weekly_goal=True)

        job.title = safe_agent2.title[:160]
        job.used_fallback = used_fallback
        job.status = "done"
        job.progress_pct = 100
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
    except Exception as exc:
        logger.exception("Analysis pipeline failed", extra={"extra_data": {"job_id": job_id}})
        db.rollback()
        failed_job = db.get(AnalysisJob, job_id)
        if failed_job:
            failed_job.status = "failed"
            failed_job.error_code = "PIPELINE_ERROR"
            failed_job.error_message = str(exc)[:400]
            db.add(failed_job)
            db.commit()
    finally:
        db.close()
