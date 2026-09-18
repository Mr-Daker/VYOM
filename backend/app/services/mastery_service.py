from app.services.base import BaseService
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.competency_repository import CompetencyRepository
from app.models.all_models import StudentMastery, utc_now
from app.schemas.mastery import StudentMasteryCreate
from app.core.exceptions import AppException
from uuid import UUID

class MasteryService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.mastery_repo = MasteryRepository(db)
        self.student_repo = StudentRepository(db)
        self.comp_repo = CompetencyRepository(db)

    def _ensure_student(self, student_id: UUID):
        if not self.student_repo.get_by_id(student_id):
            raise AppException("NOT_FOUND", "Student not found", 404)

    def _ensure_competency(self, comp_id: UUID):
        if not self.comp_repo.get_by_id(comp_id):
            raise AppException("NOT_FOUND", "Competency not found", 404)

    def upsert_mastery(self, student_id: UUID, schema: StudentMasteryCreate):
        self._ensure_student(student_id)
        self._ensure_competency(schema.competency_id)

        try:
            existing = self.mastery_repo.get_by_student_and_comp(student_id, schema.competency_id)
            if existing:
                existing.score = schema.score
                existing.state = schema.state
                existing.confidence = schema.confidence
                existing.last_updated = utc_now()
                m = existing
                self.db.flush()
            else:
                m = StudentMastery(student_id=student_id, **schema.model_dump())
                self.mastery_repo.add(m)
            self.db.commit()
            self.db.refresh(m)
            return m
        except Exception as e:
            self.db.rollback()
            raise e

    def get_student_mastery(self, student_id: UUID):
        self._ensure_student(student_id)
        return self.mastery_repo.get_by_student(student_id)
        
    def get_student_mastery_by_comp(self, student_id: UUID, comp_id: UUID):
        self._ensure_student(student_id)
        m = self.mastery_repo.get_by_student_and_comp(student_id, comp_id)
        if not m:
            raise AppException("NOT_FOUND", "Mastery not found", 404)
        return m
