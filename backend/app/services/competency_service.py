from app.services.base import BaseService
from app.repositories.competency_repository import CompetencyRepository
from app.models.all_models import Competency, CompetencyPrerequisite
from app.schemas.competency import CompetencyCreate, CompetencyPrerequisiteCreate
from app.core.exceptions import AppException
from uuid import UUID

class CompetencyService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.comp_repo = CompetencyRepository(db)

    def create_competency(self, schema: CompetencyCreate):
        c = Competency(**schema.model_dump())
        try:
            self.comp_repo.add(c)
            self.db.commit()
            self.db.refresh(c)
            return c
        except Exception as e:
            self.db.rollback()
            raise e

    def get_competencies(self, subject: str = None, grade: int = None):
        return self.comp_repo.get_all(subject, grade)

    def get_competency(self, comp_id: UUID):
        c = self.comp_repo.get_by_id(comp_id)
        if not c:
            raise AppException("NOT_FOUND", "Competency not found", 404)
        return c

    def add_prerequisite(self, comp_id: UUID, schema: CompetencyPrerequisiteCreate):
        self.get_competency(comp_id)
        self.get_competency(schema.prerequisite_competency_id)
        
        p = CompetencyPrerequisite(competency_id=comp_id, prerequisite_competency_id=schema.prerequisite_competency_id)
        try:
            self.comp_repo.add_prerequisite(p)
            self.db.commit()
            self.db.refresh(p)
            return p
        except Exception as e:
            self.db.rollback()
            raise e

    def get_prerequisites(self, comp_id: UUID):
        self.get_competency(comp_id)
        return self.comp_repo.get_prerequisites(comp_id)
