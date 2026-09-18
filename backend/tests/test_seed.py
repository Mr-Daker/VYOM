import pytest
from app.db.session import SessionLocal
from app.models.all_models import Student, ClassSession, Competency, AttendanceRecord, StudentMastery, MasteryEvidence
from app.db.seed import run_seed

def test_seed_verification():
    # 1. We must run the seed inside the test to avoid skipping
    run_seed()
    
    db = SessionLocal()
    students = db.query(Student).all()
        
    assert len(students) == 35
    grades = [s.grade for s in students]
    assert 1 in grades and 2 in grades and 3 in grades
    
    rajkumar = db.query(Student).filter(Student.name == "Rajkumar").first()
    assert rajkumar is not None
    assert rajkumar.grade == 2

    # Verify competencies
    comps = db.query(Competency).all()
    assert len(comps) >= 8

    # Verify prerequisite chain NUM_ADD_2D -> NUM_SUB_2D
    c_add = db.query(Competency).filter(Competency.code == "NUM_ADD_2D").first()
    c_sub = db.query(Competency).filter(Competency.code == "NUM_SUB_2D").first()
    
    # Check mastery
    rm = db.query(StudentMastery).filter(StudentMastery.student_id == rajkumar.id, StudentMastery.competency_id == c_add.id).first()
    assert rm is not None
    assert rm.score == 0.48

    # Check history
    atts = db.query(AttendanceRecord).filter(AttendanceRecord.student_id == rajkumar.id).join(ClassSession).order_by(ClassSession.date).all()
    assert len(atts) >= 4
    
    assert atts[-4].status.value == "present"  # Monday
    assert atts[-3].status.value == "absent"   # Tuesday
    assert atts[-2].status.value == "absent"   # Wednesday
    assert atts[-1].status.value == "present"  # Thursday

    # Verify target competencies on those sessions
    sessions = db.query(ClassSession).filter(ClassSession.classroom_id == rajkumar.classroom_id).order_by(ClassSession.date).all()
    assert sessions[-4].target_competency_id == c_add.id
    assert sessions[-1].target_competency_id == c_sub.id

    # Verify varied attendance exists (at least one late, one absent somewhere else)
    all_atts = db.query(AttendanceRecord).filter(AttendanceRecord.student_id != rajkumar.id).all()
    statuses = set([a.status.value for a in all_atts])
    assert "late" in statuses
    assert "absent" in statuses

    # Varied mastery states
    all_mastery = db.query(StudentMastery).all()
    states = set([m.state.value for m in all_mastery])
    assert "unknown" in states
    assert "needs_support" in states
    assert "mastered" in states

    # Meaningful evidence
    evs = db.query(MasteryEvidence).all()
    assert len(evs) > 0
    ev_sources = set([e.source_type.value for e in evs])
    assert len(ev_sources) > 1

    # Idempotency check
    run_seed()
    students_after = db.query(Student).all()
    assert len(students_after) == 35 # Should not duplicate
