from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app.schemas.priority import SessionPriorityResponse, GeneratePriorityRequest, ReorderPriorityRequest
from app.services.teacher_priority_service import TeacherPriorityService

router = APIRouter()

@router.post("/{session_id}/priorities/generate", response_model=SessionPriorityResponse)
def generate_priority(session_id: UUID, req: GeneratePriorityRequest, db: Session = Depends(get_db)):
    svc = TeacherPriorityService(db)
    return svc.generate_priorities(session_id, req)

@router.get("/{session_id}/priorities", response_model=SessionPriorityResponse)
def get_priorities(session_id: UUID, db: Session = Depends(get_db)):
    svc = TeacherPriorityService(db)
    return svc.get_priorities(session_id)

@router.post("/{session_id}/priorities/reorder", response_model=SessionPriorityResponse)
def reorder_priority(session_id: UUID, req: ReorderPriorityRequest, db: Session = Depends(get_db)):
    svc = TeacherPriorityService(db)
    return svc.reorder_priority(session_id, req)
