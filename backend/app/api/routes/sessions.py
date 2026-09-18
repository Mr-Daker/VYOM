from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.session_service import SessionService
from app.schemas.session import ClassSessionCreate, ClassSessionUpdate, ClassSessionResponse
from uuid import UUID

router = APIRouter()

@router.post("/classrooms/{classroom_id}/sessions", response_model=ClassSessionResponse)
def create_session(classroom_id: UUID, schema: ClassSessionCreate, db: Session = Depends(get_db)):
    return SessionService(db).create_session(classroom_id, schema)

@router.get("/classrooms/{classroom_id}/sessions", response_model=list[ClassSessionResponse])
def get_sessions(classroom_id: UUID, db: Session = Depends(get_db)):
    return SessionService(db).get_sessions(classroom_id)

@router.get("/sessions/{session_id}", response_model=ClassSessionResponse)
def get_session(session_id: UUID, db: Session = Depends(get_db)):
    return SessionService(db).get_session(session_id)

@router.patch("/sessions/{session_id}", response_model=ClassSessionResponse)
def update_session(session_id: UUID, schema: ClassSessionUpdate, db: Session = Depends(get_db)):
    return SessionService(db).update_session(session_id, schema)
