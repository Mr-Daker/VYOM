import pytest
import uuid
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from app.db.seed import run_seed
from app.models.all_models import Student, ClassSession, Competency, AttendanceRecord, StudentMastery, MasteryEvidence, LearningGroup

pytestmark = pytest.mark.postgres

def test_seed_verification(migrated_postgres_engine):
    with migrated_postgres_engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar()

    assert db_name.endswith("_test")

    TestSessionLocal = sessionmaker(
        bind=migrated_postgres_engine,
        autocommit=False,
        autoflush=False,
    )

    run_seed(session_factory=TestSessionLocal)

    db = TestSessionLocal()
    students = db.query(Student).all()
        
    assert len(students) == 35
    grades = [s.grade for s in students]
    assert 1 in grades and 2 in grades and 3 in grades
    
    rajkumar = db.query(Student).filter(Student.name == "Rajkumar").first()
    assert rajkumar is not None
    assert rajkumar.grade == 2

    comps = db.query(Competency).all()
    assert len(comps) >= 8

    c_add = db.query(Competency).filter(Competency.code == "NUM_ADD_2D").first()
    c_sub = db.query(Competency).filter(Competency.code == "NUM_SUB_2D").first()
    
    rm = db.query(StudentMastery).filter(StudentMastery.student_id == rajkumar.id, StudentMastery.competency_id == c_add.id).first()
    assert rm is not None
    assert rm.score == 0.48

    atts = db.query(AttendanceRecord).filter(AttendanceRecord.student_id == rajkumar.id).join(ClassSession).order_by(ClassSession.date).all()
    assert len(atts) >= 4
    
    # Values don't have .value because we modified the enums
    assert atts[-4].status == "present"  # Monday
    assert atts[-3].status == "absent"   # Tuesday
    assert atts[-2].status == "absent"   # Wednesday
    assert atts[-1].status == "present"  # Thursday

    sessions = db.query(ClassSession).filter(ClassSession.classroom_id == rajkumar.classroom_id).order_by(ClassSession.date).all()
    assert sessions[-4].target_competency_id == c_add.id
    assert sessions[-1].target_competency_id == c_sub.id

    all_atts = db.query(AttendanceRecord).filter(AttendanceRecord.student_id != rajkumar.id).all()
    statuses = set([a.status for a in all_atts])
    assert "late" in statuses
    assert "absent" in statuses

    all_mastery = db.query(StudentMastery).all()
    states = set([m.state for m in all_mastery])
    assert "unknown" in states
    assert "needs_support" in states
    assert "mastered" in states

    evs = db.query(MasteryEvidence).all()
    assert len(evs) > 0
    ev_sources = set([e.source_type for e in evs])
    assert len(ev_sources) > 1

    # Idempotency check
    run_seed(session_factory=TestSessionLocal)
    students_after = db.query(Student).all()
    assert len(students_after) == 35 # Should not duplicate
