"""Protected /api/* routes."""

from fastapi import APIRouter, Depends

from app.api.patients import router as patients_router
from app.api.visits import router as visits_router
from app.auth.middleware import get_current_clinician
from app.auth.schemas import ClinicianOut
from app.db.models import Clinician

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(visits_router)
router.include_router(patients_router)


@router.get("/me", response_model=ClinicianOut)
def get_me(
    clinician: Clinician = Depends(get_current_clinician),
) -> ClinicianOut:
    """Return the currently authenticated clinician profile."""
    return ClinicianOut.model_validate(clinician)
