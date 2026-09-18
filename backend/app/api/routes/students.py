from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.student_service import StudentService
from app.schemas.student import StudentCreate, StudentUpdate, StudentResponse, StudentBulkCreate
from uuid import UUID

router = APIRouter()

@router.post("/classrooms/{classroom_id}/students", response_model=StudentResponse)
def create_student(classroom_id: UUID, schema: StudentCreate, db: Session = Depends(get_db)):
    return StudentService(db).create_student(classroom_id, schema)

@router.post("/classrooms/{classroom_id}/students/bulk", response_model=list[StudentResponse])
def bulk_create_students(classroom_id: UUID, schema: StudentBulkCreate, db: Session = Depends(get_db)):
    return StudentService(db).bulk_create_students(classroom_id, schema)

@router.get("/classrooms/{classroom_id}/students", response_model=list[StudentResponse])
def get_students(classroom_id: UUID, db: Session = Depends(get_db)):
    return StudentService(db).get_students(classroom_id)

@router.get("/students/{student_id}", response_model=StudentResponse)
def get_student(student_id: UUID, db: Session = Depends(get_db)):
    return StudentService(db).get_student(student_id)

@router.patch("/students/{student_id}", response_model=StudentResponse)
def update_student(student_id: UUID, schema: StudentUpdate, db: Session = Depends(get_db)):
    return StudentService(db).update_student(student_id, schema)
