from app.services.base import BaseService
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.student_repository import StudentRepository
from app.models.all_models import AttendanceRecord
from app.schemas.attendance import AttendanceBulkCreate
from app.core.exceptions import AppException
from uuid import UUID

class AttendanceService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.att_repo = AttendanceRepository(db)
        self.session_repo = SessionRepository(db)
        self.student_repo = StudentRepository(db)

    def bulk_attendance(self, session_id: UUID, schema: AttendanceBulkCreate):
        s = self.session_repo.get_by_id(session_id)
        if not s:
            raise AppException("NOT_FOUND", "Session not found", 404)
        
        student_ids = [r.student_id for r in schema.records]
        
        # Explicit duplicate check
        if len(student_ids) != len(set(student_ids)):
            raise AppException("VALIDATION_ERROR", "Duplicate student_id found in request", 400)
            
        valid_students = [st for st in [self.student_repo.get_by_id(sid) for sid in student_ids] if st and st.classroom_id == s.classroom_id]
        if len(valid_students) != len(student_ids):
            raise AppException("VALIDATION_ERROR", "Attendance can only reference students in the session's classroom", 400)
            
        try:
            res = []
            for r in schema.records:
                existing = self.att_repo.get_by_student_and_session(r.student_id, session_id)
                if existing:
                    existing.status = r.status
                    res.append(existing)
                else:
                    new_att = AttendanceRecord(class_session_id=session_id, student_id=r.student_id, status=r.status)
                    self.att_repo.add(new_att)
                    res.append(new_att)
            self.db.commit()
            return res
        except Exception as e:
            self.db.rollback()
            raise e

    def get_attendance(self, session_id: UUID):
        if not self.session_repo.get_by_id(session_id):
            raise AppException("NOT_FOUND", "Session not found", 404)
        return self.att_repo.get_by_session(session_id)
