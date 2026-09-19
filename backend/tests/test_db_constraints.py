import pytest
pytestmark = pytest.mark.postgres
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError
from app.models.all_models import Base, StudentMastery, Student, Classroom, Competency, User, CompetencyPrerequisite, ClassSession, MasteryEvidence, AttendanceRecord
from app.models.enums import UserRole, MasteryState, EvidenceSource, AttendanceStatus, SessionStatus
import uuid

# These tests directly bind to PostgreSQL to verify actual native checks.
# If testing against sqlite, some check constraints might pass silently or throw different errors.
DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@db_test:5432/saarthi_test")

@pytest.fixture(scope="module")
def pg_session():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_db_mastery_duplicate(pg_session):
    u = User(name="T", email=f"{uuid.uuid4()}@t", password_hash="h", role=UserRole.TEACHER)
    pg_session.add(u)
    pg_session.flush()
    c = Classroom(teacher_id=u.id, name="C", default_duration_minutes=45, max_groups=2)
    pg_session.add(c)
    pg_session.flush()
    s = Student(classroom_id=c.id, name="S", grade=1)
    pg_session.add(s)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N", grade=1)
    pg_session.add(comp)
    pg_session.commit()

    m1 = StudentMastery(student_id=s.id, competency_id=comp.id, score=0.5, state=MasteryState.DEVELOPING)
    pg_session.add(m1)
    pg_session.commit()

    m2 = StudentMastery(student_id=s.id, competency_id=comp.id, score=0.6, state=MasteryState.DEVELOPING)
    pg_session.add(m2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_mastery_score_bounds(pg_session):
    s = pg_session.query(Student).first()
    comp = pg_session.query(Competency).first()
    
    m = StudentMastery(student_id=s.id, competency_id=comp.id, score=1.5, state=MasteryState.DEVELOPING)
    pg_session.add(m)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_evidence_score_bounds(pg_session):
    s = pg_session.query(Student).first()
    comp = pg_session.query(Competency).first()
    
    e = MasteryEvidence(student_id=s.id, competency_id=comp.id, source_type=EvidenceSource.MANUAL_ASSESSMENT, score=-0.1)
    pg_session.add(e)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_student_invalid_grade(pg_session):
    c = pg_session.query(Classroom).first()
    s = Student(classroom_id=c.id, name="Bad", grade=4)
    pg_session.add(s)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_self_prerequisite(pg_session):
    comp = pg_session.query(Competency).first()
    p = CompetencyPrerequisite(competency_id=comp.id, prerequisite_competency_id=comp.id)
    pg_session.add(p)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_duplicate_attendance(pg_session):
    c = pg_session.query(Classroom).first()
    s = pg_session.query(Student).first()
    sess = ClassSession(classroom_id=c.id, duration_minutes=45, status=SessionStatus.DRAFT)
    pg_session.add(sess)
    pg_session.commit()

    a1 = AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT)
    pg_session.add(a1)
    pg_session.commit()

    a2 = AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.ABSENT)
    pg_session.add(a2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_session_poison_recovery(pg_session):
    # If a commit fails with IntegrityError, the session should be usable after rollback
    c = pg_session.query(Classroom).first()
    
    # Try bad grade
    s = Student(classroom_id=c.id, name="Bad", grade=5)
    pg_session.add(s)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()
    
    # Session is unpoisoned, can insert good row
    s_good = Student(classroom_id=c.id, name="Good", grade=2)
    pg_session.add(s_good)
    pg_session.commit()
    assert s_good.id is not None
