"""Visit ingestion and YouCam analysis pipeline endpoint (POST /api/visits)."""

from datetime import date
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import CLINICAL_DISCLAIMER
from app.api.schemas import VisitOut
from app.auth.middleware import get_current_clinician
from app.config import get_settings
from app.db.models import Clinician, ConcernScore, Patient, Visit
from app.db.session import get_db
from app.domain.concerns import ANALYSIS_VERSION, CONCERN_LIST
from app.services.storage import PrivateStorageService
from app.services.youcam import (
    YouCamClientProtocol,
    YouCamError,
    YouCamTaskFailedError,
    get_youcam_client,
    parse_youcam_raw_result,
)

router = APIRouter(prefix="/visits", tags=["visits"])


def get_storage_service() -> PrivateStorageService:
    """Return private storage service instance."""
    return PrivateStorageService()


def get_youcam_service() -> YouCamClientProtocol:
    """Return YouCam client chosen by ALLOW_LIVE_CALLS."""
    return get_youcam_client()


@router.post("", response_model=VisitOut, status_code=status.HTTP_201_CREATED)
async def create_visit(
    patient_id: uuid.UUID = Form(...),
    visit_date: date | None = Form(default=None),
    chief_complaint: str | None = Form(default=None),
    routine_text: str | None = Form(default=None),
    treatment_changes: str | None = Form(default=None),
    image: UploadFile = File(...),
    clinician: Clinician = Depends(get_current_clinician),
    db: Session = Depends(get_db),
    storage: PrivateStorageService = Depends(get_storage_service),
    youcam: YouCamClientProtocol = Depends(get_youcam_service),
) -> VisitOut | JSONResponse:
    """Ingest a patient visit selfie, run the YouCam skin analysis pipeline, and persist scores."""
    patient = db.get(Patient, patient_id)
    if patient is None or patient.clinic_id != clinician.clinic_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found in clinician's clinic.",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    visit_id = uuid.uuid4()
    filename = image.filename or "selfie.jpg"
    content_type = image.content_type or "image/jpeg"

    # Store patient selfie in private storage (never a public URL)
    image_storage_key = storage.store_visit_selfie(
        patient_id=patient.id,
        visit_id=visit_id,
        image_bytes=image_bytes,
        filename=filename,
    )

    visit = Visit(
        id=visit_id,
        patient_id=patient.id,
        visit_date=visit_date or date.today(),
        chief_complaint=chief_complaint,
        routine_text=routine_text,
        treatment_changes=treatment_changes,
        analysis_version=ANALYSIS_VERSION,
        image_storage_key=image_storage_key,
        youcam_status="pending",
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    settings = get_settings()

    try:
        file_id = await youcam.upload_file(
            image_bytes,
            filename=filename,
            content_type=content_type,
        )
        visit.youcam_file_id = file_id

        task_id = await youcam.create_task(
            file_id,
            dst_actions=CONCERN_LIST,
            prerender=True,
        )
        visit.youcam_task_id = task_id
        db.commit()

        raw_result = await youcam.poll_task(task_id)
        parsed_scores = parse_youcam_raw_result(raw_result)

        visit.raw_result = raw_result
        visit.youcam_status = "success"

        for item in parsed_scores:
            mask_storage_key = await storage.cache_concern_mask(
                patient_id=patient.id,
                visit_id=visit.id,
                concern=item.concern,
                mask_url=item.mask_url,
                allow_live_fetch=settings.ALLOW_LIVE_CALLS,
            )
            score_row = ConcernScore(
                visit_id=visit.id,
                concern=item.concern,
                score=item.score,
                severity=item.severity,
                mask_url=item.mask_url,
                mask_storage_key=mask_storage_key,
            )
            db.add(score_row)

        db.commit()
        db.refresh(visit)
        return VisitOut.model_validate(visit)

    except YouCamTaskFailedError as exc:
        visit.youcam_status = "failed"
        if exc.task_id and not visit.youcam_task_id:
            visit.youcam_task_id = exc.task_id
        if exc.raw_result is not None:
            visit.raw_result = exc.raw_result
        db.commit()
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "detail": str(exc),
                "visit_id": str(visit.id),
                "youcam_status": "failed",
                "disclaimer": CLINICAL_DISCLAIMER,
            },
        )
    except YouCamError as exc:
        visit.youcam_status = "failed"
        db.commit()
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "detail": str(exc),
                "visit_id": str(visit.id),
                "youcam_status": "failed",
                "disclaimer": CLINICAL_DISCLAIMER,
            },
        )
