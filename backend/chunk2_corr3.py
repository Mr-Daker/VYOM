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

# 1. Rajkumar likely gap
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
    
    base_t = datetime.now(timezone.utc)
    mon = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=5))
    tue = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=4))
    wed = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=3))
    thu = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
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

# 2. Aditi high mastery despite absence = READY
def test_aditi_high_mastery_despite_absence_is_ready(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="Aditi", grade=2)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED))
    
    base_t = datetime.now(timezone.utc)
    past = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
    db_session.add_all([past, curr])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["classification"] == GapClassification.READY
    assert res.json()["students"][0]["overall_status"] == OverallReadinessStatus.READY

# 3. Kiran direct insufficient + transitive confirmed gap
def test_kiran_direct_insufficient_transitive_confirmed(client, db_session):
    c = setup_base(db_session)
    c_pv = Competency(code=f"PV{uuid.uuid4()}", subject="math", name="Place Value")
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    kiran = Student(classroom_id=c.id, name="Kiran", grade=2)
    db_session.add_all([c_pv, c_add, c_sub, kiran])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_add.id, prerequisite_competency_id=c_pv.id))
    
    db_session.add(StudentMastery(student_id=kiran.id, competency_id=c_pv.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=kiran.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    
    assert st["direct_prerequisites"][0]["classification"] == GapClassification.INSUFFICIENT_EVIDENCE
    assert st["transitive_context"][0]["classification"] == GapClassification.CONFIRMED_GAP
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_CHECK

# 4. no-prerequisite target
def test_no_prerequisite_target(client, db_session):
    c = setup_base(db_session)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="Root", grade=1)
    s = Student(classroom_id=c.id, name="S1", grade=1)
    db_session.add_all([comp, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=comp.id, duration_minutes=45, status=SessionStatus.DRAFT)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["overall_status"] == OverallReadinessStatus.NO_PREREQUISITES

# 5. missing mastery
def test_missing_mastery(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["classification"] == GapClassification.INSUFFICIENT_EVIDENCE

# 6. confirmed gap
def test_confirmed_gap(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["classification"] == GapClassification.CONFIRMED_GAP

# 7. developing + full attendance
def test_developing_full_attendance(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.55, state=MasteryState.DEVELOPING))
    
    base_t = datetime.now(timezone.utc)
    past = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
    db_session.add_all([past, curr])
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    st = res.json()["students"][0]
    assert st["direct_prerequisites"][0]["classification"] == GapClassification.DEVELOPING
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_CHECK

# 8. developing + recent absence
def test_developing_recent_absence(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.55, state=MasteryState.DEVELOPING))
    
    base_t = datetime.now(timezone.utc)
    past = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
    db_session.add_all([past, curr])
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["classification"] == GapClassification.LIKELY_GAP

# 9. developing + old absence outside lookback
def test_developing_old_absence(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.55, state=MasteryState.DEVELOPING))
    
    base_t = datetime.now(timezone.utc)
    # Absent 90 days ago
    past_90 = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=90))
    # Present 2 days ago
    past_2 = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
    db_session.add_all([past_90, past_2, curr])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past_90.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past_2.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    # Should ignore the 90 day old absence due to 30 day lookback default
    assert res.json()["students"][0]["direct_prerequisites"][0]["classification"] == GapClassification.DEVELOPING

# 10. stale mastery relative to session.date
def test_stale_mastery(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    m = StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED)
    db_session.add(m)
    db_session.commit()
    
    base_t = datetime.now(timezone.utc)
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, date=base_t)
    db_session.add(sess)
    db_session.commit()
    
    # updated 40 days before session.date
    m.last_updated = sess.date - timedelta(days=40)
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["classification"] == GapClassification.INSUFFICIENT_EVIDENCE
    assert res.json()["students"][0]["direct_prerequisites"][0]["stale"] == True

# 11. current absent
def test_current_absent(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["analysis_status"] == StudentAnalysisStatus.NOT_CURRENTLY_AVAILABLE

# 12. current attendance missing
def test_current_attendance_missing(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    # No attendance record
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["analysis_status"] == StudentAnalysisStatus.CURRENT_ATTENDANCE_UNKNOWN

# 13. current late
def test_current_late(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.LATE))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["analysis_status"] == StudentAnalysisStatus.ANALYZED
    assert res.json()["students"][0]["overall_status"] == OverallReadinessStatus.READY

# 14. inactive student excluded
def test_inactive_student_excluded(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1, active=False)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert len(res.json()["students"]) == 0
    assert res.json()["summary"]["students_total"] == 0

# 15. session missing
def test_session_missing(client):
    res = client.post(f"/api/v1/sessions/{uuid.uuid4()}/detect-gaps")
    assert res.status_code == 404

# 16. session target missing
def test_session_target_missing(client, db_session):
    c = setup_base(db_session)
    sess = ClassSession(classroom_id=c.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.status_code == 400

# 17. direct vs transitive precedence
def test_direct_vs_transitive_precedence(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_c, s])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_c.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_b.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_c.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.json()["students"][0]["overall_status"] == OverallReadinessStatus.READY
    # B is ready, A has no mastery, so student is overall ready.

# 18. multiple direct prerequisites
def test_multiple_direct_prerequisites(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_tar = Competency(code=f"TAR{uuid.uuid4()}", subject="math", name="TAR")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_tar, s])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_tar.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_tar.id, prerequisite_competency_id=c_b.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_b.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_tar.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    assert st["overall_status"] == OverallReadinessStatus.NEEDS_SUPPORT
    assert st["recovery_recommended"] == True

# 19. cycle protection
def test_cycle_protection(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_c, s])
    db_session.commit()
    
    # C -> B -> A -> C
    db_session.add(CompetencyPrerequisite(competency_id=c_c.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_a.id, prerequisite_competency_id=c_c.id))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_c.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    assert res.status_code == 200
    assert len(res.json()["metadata"]["warnings"]) > 0

# 20. target does not appear in transitive set
def test_target_not_in_transitive(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_a.id, prerequisite_competency_id=c_b.id))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    t_ids = [t["competency_id"] for t in st["transitive_context"]]
    assert str(c_b.id) not in t_ids

# 21. no duplicate prerequisite IDs
def test_no_duplicate_prerequisite_ids(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_c, s])
    db_session.commit()
    
    # C -> B -> A and C -> A
    db_session.add(CompetencyPrerequisite(competency_id=c_c.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_c.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_c.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    st = res.json()["students"][0]
    # A is a direct prereq, it should not also appear in transitive context
    d_ids = [d["competency_id"] for d in st["direct_prerequisites"]]
    t_ids = [t["competency_id"] for t in st["transitive_context"]]
    assert set(d_ids).intersection(set(t_ids)) == set()

# 22. cross-classroom isolation
def test_cross_classroom_isolation(client, db_session):
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
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess1.id}/detect-gaps")
    students = res.json()["students"]
    assert len(students) == 1
    assert students[0]["student_id"] == str(s1.id)

# 23. future session ignored
def test_future_session_ignored(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    base_t = datetime.now(timezone.utc)
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, date=base_t)
    future = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t + timedelta(days=2))
    db_session.add_all([curr, future])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=future.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    st = res.json()["students"][0]
    assert st["direct_prerequisites"][0]["relevant_sessions"] == 0

# 24. non-completed session ignored
def test_non_completed_session_ignored(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    base_t = datetime.now(timezone.utc)
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, date=base_t)
    past_draft = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t - timedelta(days=2))
    db_session.add_all([curr, past_draft])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past_draft.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["relevant_sessions"] == 0

# 25. unrelated competency session ignored
def test_unrelated_competency_session_ignored(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C") # unrelated
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_c, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    base_t = datetime.now(timezone.utc)
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, date=base_t)
    past_c = ClassSession(classroom_id=c.id, target_competency_id=c_c.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    db_session.add_all([curr, past_c])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past_c.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["relevant_sessions"] == 0

# 26. old session outside lookback ignored
def test_old_session_outside_lookback_ignored(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    base_t = datetime.now(timezone.utc)
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, date=base_t)
    past_90 = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=90))
    db_session.add_all([curr, past_90])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past_90.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    assert res.json()["students"][0]["direct_prerequisites"][0]["relevant_sessions"] == 0

# 27. historical unrecorded attendance handled
def test_historical_unrecorded_attendance_handled(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    base_t = datetime.now(timezone.utc)
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, date=base_t)
    past = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    db_session.add_all([curr, past])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    # NO attendance record for past session
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps")
    st = res.json()["students"][0]
    dp = st["direct_prerequisites"][0]
    assert dp["relevant_sessions"] == 1
    assert dp["attendance_unrecorded_sessions"] == 1

# 28. summary counts consistent
def test_summary_counts_consistent(client, db_session):
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
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    # s2 not recorded
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    summ = res.json()["summary"]
    assert summ["students_total"] == 2
    assert summ["students_analyzed"] == 1
    assert summ["attendance_unknown"] == 1
    assert summ["students_analyzed"] == summ["ready"] + summ["needs_support"] + summ["needs_check"] + summ["no_prerequisites"]

# 29. deterministic repeated calls
def test_deterministic_repeated_calls(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.48, state=MasteryState.DEVELOPING))
    
    base_t = datetime.now(timezone.utc)
    past = ClassSession(classroom_id=c.id, target_competency_id=c_a.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=2))
    curr = ClassSession(classroom_id=c.id, target_competency_id=c_b.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
    db_session.add_all([past, curr])
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=past.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=curr.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res1 = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps").json()
    res2 = client.post(f"/api/v1/sessions/{curr.id}/detect-gaps").json()
    assert res1 == res2
""")
