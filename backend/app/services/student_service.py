from app.services.base import BaseService
from app.repositories.student_repository import StudentRepository
from app.repositories.classroom_repository import ClassroomRepository
from app.models.all_models import Student
from app.schemas.student import StudentCreate, StudentUpdate, StudentBulkCreate
from app.core.exceptions import AppException
from uuid import UUID

class StudentService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.student_repo = StudentRepository(db)
        self.class_repo = ClassroomRepository(db)

    def _ensure_classroom(self, classroom_id: UUID):
        if not self.class_repo.get_by_id(classroom_id):
            raise AppException("NOT_FOUND", "Classroom not found", 404)

    def create_student(self, classroom_id: UUID, schema: StudentCreate):
        self._ensure_classroom(classroom_id)
        s = Student(classroom_id=classroom_id, **schema.model_dump())
        try:
            self.student_repo.add(s)
            self.db.commit()
            self.db.refresh(s)
            return s
        except Exception as e:
            self.db.rollback()
            raise e

    def bulk_create_students(self, classroom_id: UUID, schema: StudentBulkCreate):
        self._ensure_classroom(classroom_id)
        students = [Student(classroom_id=classroom_id, **s.model_dump()) for s in schema.students]
        try:
            self.student_repo.add_all(students)
            self.db.commit()
            return students
        except Exception as e:
            self.db.rollback()
            raise e

    def get_students(self, classroom_id: UUID):
        self._ensure_classroom(classroom_id)
        return self.student_repo.get_by_classroom(classroom_id)

    def get_student(self, student_id: UUID):
        s = self.student_repo.get_by_id(student_id)
        if not s:
            raise AppException("NOT_FOUND", "Student not found", 404)
        return s

    def update_student(self, student_id: UUID, schema: StudentUpdate):
        s = self.get_student(student_id)
        try:
            for k, v in schema.model_dump(exclude_unset=True).items():
                setattr(s, k, v)
            self.db.commit()
            self.db.refresh(s)
            return s
        except Exception as e:
            self.db.rollback()
            raise e
