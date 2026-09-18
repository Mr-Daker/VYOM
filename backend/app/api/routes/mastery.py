from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.mastery_service import MasteryService
from app.schemas.mastery import StudentMasteryCreate, StudentMasteryResponse
from uuid import UUID

router = APIRouter()

@router.post("/{student_id}/mastery", response_model=StudentMasteryResponse)
def create_mastery(student_id: UUID, schema: StudentMasteryCreate, db: Session = Depends(get_db)):
    return MasteryService(db).upsert_mastery(student_id, schema)

@router.get("/{student_id}/mastery", response_model=list[StudentMasteryResponse])
def get_masteries(student_id: UUID, db: Session = Depends(get_db)):
    return MasteryService(db).get_student_mastery(student_id)

@router.get("/{student_id}/mastery/{competency_id}", response_model=StudentMasteryResponse)
def get_mastery(student_id: UUID, competency_id: UUID, db: Session = Depends(get_db)):
    return MasteryService(db).get_student_mastery_by_comp(student_id, competency_id)
