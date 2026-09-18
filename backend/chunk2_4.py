with open("tests/test_gap_detection.py", "w") as f:
    f.write("""import pytest
import uuid
from datetime import datetime, timezone, timedelta
from app.models.all_models import User, Classroom, Student, Competency, CompetencyPrerequisite, ClassSession, AttendanceRecord, StudentMastery
from app.models.enums import UserRole, AttendanceStatus, SessionStatus, MasteryState
from app.schemas.gap_detection import GapClassification, OverallReadinessStatus, StudentAnalysisStatus

def setup_base(db):
    t = User(name="T", email=f"{uuid.uuid4()}@t.com", password_hash="h", role=UserRole.TEACHER)
    db.add(t)
    db.commit()
    c = Classroom(teacher_id=t.id, name="Math", default_duration_minutes=45, max_groups=4)
    db.add(c)
    db.commit()
    return c

def test_no_prerequisites(client, db_session):
    c = setup_base(db_session)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="Root", grade=1)
    s = Student(classroom_id=c.id, name="S1", grade=1)
    db_session.add_all([comp, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=comp.id, duration_minutes=45, status=SessionStatus.DRAFT)
    db_session.add(sess)
    db_session.commit()
    
    # Current attendance
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["no_prerequisites"] == 1
    assert data["students"][0]["overall_status"] == OverallReadinessStatus.NO_PREREQUISITES

def test_missing_mastery_is_insufficient(client, db_session):
    c = setup_base(db_session)
    comp_a = Competency(code=f"C{uuid.uuid4()}", subject="math", name="A")
    comp_b = Competency(code=f"C{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([comp_a, comp_b, s])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=comp_b.id, prerequisite_competency_id=comp_a.id))
    sess = ClassSession(classroom_id=c.id, target_competency_id=comp_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.status_code == 200
    st = res.json()["students"][0]
    assert st["direct_prerequisites"][0]["classification"] == GapClassification.INSUFFICIENT_EVIDENCE
    assert st["assessment_recommended"] == True

def test_rajkumar_likely_gap(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    raj = Student(classroom_id=c.id, name="Rajkumar", grade=2)
    db_session.add_all([c_add, c_sub, raj])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    db_session.commit()
    
    db_session.add(StudentMastery(student_id=raj.id, competency_id=c_add.id, score=0.48, state=MasteryState.DEVELOPING))
    
    base_t = datetime.now(timezone.utc) - timedelta(days=5)
    mon = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t)
    tue = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t + timedelta(days=1))
    wed = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t + timedelta(days=2))
    thu = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t + timedelta(days=3))
    db_session.add_all([mon, tue, wed, thu])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=raj.id, class_session_id=mon.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=raj.id, class_session_id=tue.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=raj.id, class_session_id=wed.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=raj.id, class_session_id=thu.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{thu.id}/detect-gaps")
    assert res.status_code == 200
    st = res.json()["students"][0]
    
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_SUPPORT
    assert st["recovery_recommended"] == True
    dp = st["direct_prerequisites"][0]
    assert dp["classification"] == GapClassification.LIKELY_GAP
    assert dp["absent_sessions"] == 2
    assert dp["present_sessions"] == 1

def test_aditi_absence_only_still_ready(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    aditi = Student(classroom_id=c.id, name="Aditi", grade=2)
    db_session.add_all([c_add, c_sub, aditi])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    db_session.commit()
    
    # Aditi is 0.90 mastered!
    db_session.add(StudentMastery(student_id=aditi.id, competency_id=c_add.id, score=0.90, state=MasteryState.MASTERED))
    
    base_t = datetime.now(timezone.utc) - timedelta(days=2)
    tue = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t)
    thu = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t + timedelta(days=2))
    db_session.add_all([tue, thu])
    db_session.commit()
    
    # Aditi was absent
    db_session.add(AttendanceRecord(student_id=aditi.id, class_session_id=tue.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=aditi.id, class_session_id=thu.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{thu.id}/detect-gaps")
    assert res.status_code == 200
    st = res.json()["students"][0]
    assert st["overall_status"] == OverallReadinessStatus.READY
    dp = st["direct_prerequisites"][0]
    assert dp["classification"] == GapClassification.READY
    assert dp["absent_sessions"] == 1

def test_stale_mastery(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    # Stale record manually manipulated
    m = StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED)
    db_session.add(m)
    db_session.commit()
    
    # hard update last_updated to 40 days ago
    m.last_updated = datetime.now(timezone.utc) - timedelta(days=40)
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    dp = st["direct_prerequisites"][0]
    assert dp["stale"] == True
    assert dp["classification"] == GapClassification.INSUFFICIENT_EVIDENCE
    assert st["assessment_recommended"] == True

def test_current_absent_and_missing(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([c_a, c_b, s1, s2])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    
    # S1 absent, S2 not recorded
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.status_code == 200
    st1 = next(s for s in res.json()["students"] if s["student_id"] == str(s1.id))
    st2 = next(s for s in res.json()["students"] if s["student_id"] == str(s2.id))
    
    assert st1["analysis_status"] == StudentAnalysisStatus.NOT_CURRENTLY_AVAILABLE
    assert st1["overall_status"] == OverallReadinessStatus.NOT_ANALYZED
    assert st2["analysis_status"] == StudentAnalysisStatus.CURRENT_ATTENDANCE_UNKNOWN
    assert st2["overall_status"] == OverallReadinessStatus.NOT_ANALYZED

def test_developing_full_attendance(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.55, state=MasteryState.DEVELOPING))
    db_session.commit()
    
    base_t = datetime.now(timezone.utc) - timedelta(days=2)
    past_sess = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t)
    curr_sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t + timedelta(days=2))
    db_session.add_all([past_sess, curr_sess])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past_sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr_sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr_sess.id}/detect-gaps")
    st = res.json()["students"][0]
    
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_CHECK
    assert st["quick_check_recommended"] == True
    assert st["direct_prerequisites"][0]["classification"] == GapClassification.DEVELOPING

def test_confirmed_gap(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_SUPPORT
    assert st["recovery_recommended"] == True
    assert st["direct_prerequisites"][0]["classification"] == GapClassification.CONFIRMED_GAP

def test_cycle_protection(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_c, s])
    db_session.commit()
    
    # Cycle: C -> B -> A -> C
    db_session.add(CompetencyPrerequisite(competency_id=c_c.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_a.id, prerequisite_competency_id=c_c.id))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_c.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    # Should not infinite loop
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.status_code == 200
    st = res.json()["students"][0]
    assert len(st["direct_prerequisites"]) == 1 # B
    assert len(st["transitive_context"]) == 2 # A, C

def test_classroom_isolation(client, db_session):
    c1 = setup_base(db_session)
    c2 = setup_base(db_session)
    
    comp = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    db_session.add(comp)
    db_session.commit()
    
    s1 = Student(classroom_id=c1.id, name="S1", grade=1)
    s2 = Student(classroom_id=c2.id, name="S2", grade=1)
    db_session.add_all([s1, s2])
    db_session.commit()
    
    sess1 = ClassSession(classroom_id=c1.id, target_competency_id=comp.id, duration_minutes=45)
    db_session.add(sess1)
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess1.id, status=AttendanceStatus.PRESENT))
    # S2 doesn't belong here, just to be sure we don't return S2
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess1.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess1.id}/detect-gaps")
    assert res.status_code == 200
    students = res.json()["students"]
    assert len(students) == 1
    assert students[0]["student_id"] == str(s1.id)

def test_missing_session(client):
    res = client.post(f"/api/v1/sessions/{uuid.uuid4()}/detect-gaps")
    assert res.status_code == 404

def test_kiran_transitive_context(client, db_session):
    c = setup_base(db_session)
    c_pv = Competency(code=f"PV{uuid.uuid4()}", subject="math", name="Place Value")
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    kiran = Student(classroom_id=c.id, name="Kiran", grade=2)
    db_session.add_all([c_pv, c_add, c_sub, kiran])
    db_session.commit()
    
    # SUB requires ADD. ADD requires PV.
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_add.id, prerequisite_competency_id=c_pv.id))
    
    # Kiran has PV = 0.20, ADD = no record
    db_session.add(StudentMastery(student_id=kiran.id, competency_id=c_pv.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=kiran.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_CHECK
    dp = st["direct_prerequisites"][0]
    assert dp["competency_name"] == "ADD"
    assert dp["classification"] == GapClassification.INSUFFICIENT_EVIDENCE
    
    trans = st["transitive_context"][0]
    assert trans["competency_name"] == "Place Value"
    assert trans["classification"] == GapClassification.CONFIRMED_GAP

""")
