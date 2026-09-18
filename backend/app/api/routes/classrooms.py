from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.classroom_service import ClassroomService
from app.schemas.classroom import ClassroomCreate, ClassroomUpdate, ClassroomResponse
from uuid import UUID

router = APIRouter()

@router.post("", response_model=ClassroomResponse)
def create_classroom(schema: ClassroomCreate, db: Session = Depends(get_db)):
    return ClassroomService(db).create_classroom(schema)

@router.get("", response_model=list[ClassroomResponse])
def get_classrooms(db: Session = Depends(get_db)):
    return ClassroomService(db).get_classrooms()

@router.get("/{classroom_id}", response_model=ClassroomResponse)
def get_classroom(classroom_id: UUID, db: Session = Depends(get_db)):
    return ClassroomService(db).get_classroom(classroom_id)

@router.patch("/{classroom_id}", response_model=ClassroomResponse)
def update_classroom(classroom_id: UUID, schema: ClassroomUpdate, db: Session = Depends(get_db)):
    return ClassroomService(db).update_classroom(classroom_id, schema)
