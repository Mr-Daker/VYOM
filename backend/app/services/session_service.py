from app.services.base import BaseService
from app.repositories.session_repository import SessionRepository
from app.repositories.classroom_repository import ClassroomRepository
from app.repositories.competency_repository import CompetencyRepository
from app.models.all_models import ClassSession
from app.schemas.session import ClassSessionCreate, ClassSessionUpdate
from app.core.exceptions import AppException
from uuid import UUID

class SessionService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.session_repo = SessionRepository(db)
        self.class_repo = ClassroomRepository(db)
        self.comp_repo = CompetencyRepository(db)

    def _ensure_classroom(self, classroom_id: UUID):
        if not self.class_repo.get_by_id(classroom_id):
            raise AppException("NOT_FOUND", "Classroom not found", 404)

    def create_session(self, classroom_id: UUID, schema: ClassSessionCreate):
        self._ensure_classroom(classroom_id)
        if schema.target_competency_id:
            if not self.comp_repo.get_by_id(schema.target_competency_id):
                raise AppException("NOT_FOUND", "Competency not found", 404)
            
        s = ClassSession(classroom_id=classroom_id, **schema.model_dump())
        try:
            self.session_repo.add(s)
            self.db.commit()
            self.db.refresh(s)
            return s
        except Exception as e:
            self.db.rollback()
            raise e

    def get_sessions(self, classroom_id: UUID):
        self._ensure_classroom(classroom_id)
        return self.session_repo.get_by_classroom(classroom_id)

    def get_session(self, session_id: UUID):
        s = self.session_repo.get_by_id(session_id)
        if not s:
            raise AppException("NOT_FOUND", "Session not found", 404)
        return s
        
    def update_session(self, session_id: UUID, schema: ClassSessionUpdate):
        s = self.get_session(session_id)
        if schema.target_competency_id:
            if not self.comp_repo.get_by_id(schema.target_competency_id):
                raise AppException("NOT_FOUND", "Target competency not found", 404)
                
        try:
            for k, v in schema.model_dump(exclude_unset=True).items():
                setattr(s, k, v)
            self.db.commit()
            self.db.refresh(s)
            return s
        except Exception as e:
            self.db.rollback()
            raise e
