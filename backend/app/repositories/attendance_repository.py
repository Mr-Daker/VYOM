from app.repositories.base import BaseRepository
from app.models.all_models import AttendanceRecord
from uuid import UUID

class AttendanceRepository(BaseRepository):
    def get_by_student_and_session(self, student_id: UUID, session_id: UUID) -> AttendanceRecord | None:
        return self.db.query(AttendanceRecord).filter(
            AttendanceRecord.student_id == student_id,
            AttendanceRecord.class_session_id == session_id
        ).first()
        
    def get_by_session(self, session_id: UUID):
        return self.db.query(AttendanceRecord).filter(AttendanceRecord.class_session_id == session_id).all()
        
    def add(self, record: AttendanceRecord):
        self.db.add(record)
        self.db.flush()
        return record

    def get_for_students_and_sessions(self, student_ids: list[UUID], session_ids: list[UUID]):
        if not student_ids or not session_ids: return []
        return self.db.query(AttendanceRecord).filter(
            AttendanceRecord.student_id.in_(student_ids),
            AttendanceRecord.class_session_id.in_(session_ids)
        ).all()
