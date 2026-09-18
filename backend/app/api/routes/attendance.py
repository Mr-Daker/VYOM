from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.attendance_service import AttendanceService
from app.schemas.attendance import AttendanceBulkCreate, AttendanceRecordResponse
from uuid import UUID

router = APIRouter()

@router.post("/sessions/{session_id}/attendance", response_model=list[AttendanceRecordResponse])
def bulk_attendance(session_id: UUID, schema: AttendanceBulkCreate, db: Session = Depends(get_db)):
    return AttendanceService(db).bulk_attendance(session_id, schema)

@router.get("/sessions/{session_id}/attendance", response_model=list[AttendanceRecordResponse])
def get_attendance(session_id: UUID, db: Session = Depends(get_db)):
    return AttendanceService(db).get_attendance(session_id)
