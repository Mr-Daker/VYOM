import os
os.makedirs("app/repositories", exist_ok=True)

with open("app/repositories/base.py", "w") as f:
    f.write("""from sqlalchemy.orm import Session
from uuid import UUID

class BaseRepository:
    def __init__(self, db: Session):
        self.db = db
""")

with open("app/repositories/user_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import User
from uuid import UUID

class UserRepository(BaseRepository):
    def get_by_id(self, user_id: UUID) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()
        
    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()
        
    def add(self, user: User):
        self.db.add(user)
        self.db.flush()
        return user
""")

with open("app/repositories/classroom_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import Classroom
from uuid import UUID

class ClassroomRepository(BaseRepository):
    def get_by_id(self, classroom_id: UUID) -> Classroom | None:
        return self.db.query(Classroom).filter(Classroom.id == classroom_id).first()
        
    def get_all(self):
        return self.db.query(Classroom).all()
        
    def add(self, classroom: Classroom):
        self.db.add(classroom)
        self.db.flush()
        return classroom
""")

with open("app/repositories/student_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import Student
from uuid import UUID

class StudentRepository(BaseRepository):
    def get_by_id(self, student_id: UUID) -> Student | None:
        return self.db.query(Student).filter(Student.id == student_id).first()
        
    def get_by_classroom(self, classroom_id: UUID):
        return self.db.query(Student).filter(Student.classroom_id == classroom_id).all()
        
    def add(self, student: Student):
        self.db.add(student)
        self.db.flush()
        return student
        
    def add_all(self, students: list[Student]):
        self.db.add_all(students)
        self.db.flush()
        return students
""")

with open("app/repositories/competency_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import Competency, CompetencyPrerequisite
from uuid import UUID

class CompetencyRepository(BaseRepository):
    def get_by_id(self, comp_id: UUID) -> Competency | None:
        return self.db.query(Competency).filter(Competency.id == comp_id).first()
        
    def get_all(self, subject: str = None, grade: int = None):
        q = self.db.query(Competency)
        if subject: q = q.filter(Competency.subject == subject)
        if grade: q = q.filter(Competency.grade == grade)
        return q.all()
        
    def add(self, comp: Competency):
        self.db.add(comp)
        self.db.flush()
        return comp

    def add_prerequisite(self, prereq: CompetencyPrerequisite):
        self.db.add(prereq)
        self.db.flush()
        return prereq
        
    def get_prerequisites(self, comp_id: UUID):
        return self.db.query(CompetencyPrerequisite).filter(CompetencyPrerequisite.competency_id == comp_id).all()
""")

with open("app/repositories/mastery_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import StudentMastery
from uuid import UUID

class MasteryRepository(BaseRepository):
    def get_by_student_and_comp(self, student_id: UUID, comp_id: UUID) -> StudentMastery | None:
        return self.db.query(StudentMastery).filter(
            StudentMastery.student_id == student_id,
            StudentMastery.competency_id == comp_id
        ).first()
        
    def get_by_student(self, student_id: UUID):
        return self.db.query(StudentMastery).filter(StudentMastery.student_id == student_id).all()
        
    def add(self, mastery: StudentMastery):
        self.db.add(mastery)
        self.db.flush()
        return mastery
""")

with open("app/repositories/evidence_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import MasteryEvidence
from uuid import UUID

class EvidenceRepository(BaseRepository):
    def add(self, evidence: MasteryEvidence):
        self.db.add(evidence)
        self.db.flush()
        return evidence
""")

with open("app/repositories/session_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
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
""")

with open("app/repositories/attendance_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
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
""")
