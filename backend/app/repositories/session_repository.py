from app.repositories.base import BaseRepository
from app.models.all_models import ClassSession
from uuid import UUID

class SessionRepository(BaseRepository):
    def get_by_id(self, session_id: UUID) -> ClassSession | None:
        return self.db.query(ClassSession).filter(ClassSession.id == session_id).first()
        
    def get_by_classroom(self, classroom_id: UUID):
        return self.db.query(ClassSession).filter(ClassSession.classroom_id == classroom_id).all()
        
    def add(self, session: ClassSession):
        self.db.add(session)
        self.db.flush()
        return session

    def get_completed_before(self, classroom_id: UUID, before_date, since_date, target_competency_ids: list[UUID]):
        from app.models.enums import SessionStatus
        if not target_competency_ids: return []
        return self.db.query(ClassSession).filter(
            ClassSession.classroom_id == classroom_id,
            ClassSession.date < before_date,
            ClassSession.date >= since_date,
            ClassSession.target_competency_id.in_(target_competency_ids),
            ClassSession.status == SessionStatus.COMPLETED
        ).all()
