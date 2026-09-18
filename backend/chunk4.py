import os

with open("app/services/classroom_service.py", "w") as f:
    f.write("""from app.services.base import BaseService
from app.repositories.classroom_repository import ClassroomRepository
from app.repositories.user_repository import UserRepository
from app.models.all_models import Classroom
from app.schemas.classroom import ClassroomCreate, ClassroomUpdate
from app.core.exceptions import AppException
from uuid import UUID

class ClassroomService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.class_repo = ClassroomRepository(db)
        self.user_repo = UserRepository(db)

    def create_classroom(self, schema: ClassroomCreate):
        u = self.user_repo.get_by_id(schema.teacher_id)
        if not u:
            raise AppException("NOT_FOUND", "Teacher not found", 404)
        c = Classroom(**schema.model_dump())
        try:
            self.class_repo.add(c)
            self.db.commit()
            self.db.refresh(c)
            return c
        except Exception as e:
            self.db.rollback()
            raise e

    def get_classrooms(self):
        return self.class_repo.get_all()

    def get_classroom(self, classroom_id: UUID):
        c = self.class_repo.get_by_id(classroom_id)
        if not c:
            raise AppException("NOT_FOUND", "Classroom not found", 404)
        return c

    def update_classroom(self, classroom_id: UUID, schema: ClassroomUpdate):
        c = self.get_classroom(classroom_id)
        try:
            for k, v in schema.model_dump(exclude_unset=True).items():
                setattr(c, k, v)
            self.db.commit()
            self.db.refresh(c)
            return c
        except Exception as e:
            self.db.rollback()
            raise e
""")

with open("app/services/student_service.py", "w") as f:
    f.write("""from app.services.base import BaseService
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
""")

with open("app/services/competency_service.py", "w") as f:
    f.write("""from app.services.base import BaseService
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
""")

with open("app/services/mastery_service.py", "w") as f:
    f.write("""from app.services.base import BaseService
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
""")

with open("app/services/session_service.py", "w") as f:
    f.write("""from app.services.base import BaseService
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
""")

with open("app/services/attendance_service.py", "w") as f:
    f.write("""from app.services.base import BaseService
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
""")
