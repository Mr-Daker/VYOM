from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.gap_detection_service import GapDetectionService
from app.schemas.gap_detection import GapDetectionResponse
from uuid import UUID

router = APIRouter()

@router.post("/sessions/{session_id}/detect-gaps", response_model=GapDetectionResponse)
def detect_gaps(session_id: UUID, db: Session = Depends(get_db)):
    return GapDetectionService(db).detect_gaps(session_id)
