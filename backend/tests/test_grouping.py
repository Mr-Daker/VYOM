import pytest
import uuid
from datetime import datetime, timezone, timedelta
from app.models.all_models import User, Classroom, Student, Competency, CompetencyPrerequisite, ClassSession, AttendanceRecord, StudentMastery, LearningGroup, GroupMembership
from app.models.enums import UserRole, EvidenceSource, AttendanceStatus, SessionStatus, MasteryState, GroupType, CheckMode
from app.schemas.gap_detection import GapClassification, OverallReadinessStatus, StudentAnalysisStatus

def setup_base(db):
    t = User(name="T", email=f"{uuid.uuid4()}@t.com", password_hash="h", role=UserRole.TEACHER)
    db.add(t)
    db.commit()
    c = Classroom(teacher_id=t.id, name="Math", default_duration_minutes=45, max_groups=4)
    db.add(c)
    db.commit()
    return c

def test_rajkumar_recovery_addition(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"NUM_ADD_2D{uuid.uuid4()}", subject="math", name="Two-digit addition")
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    raj = Student(classroom_id=c.id, name="Rajkumar", grade=2)
    db_session.add_all([c_add, c_sub, raj])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    db_session.commit()
    
    db_session.add(StudentMastery(student_id=raj.id, competency_id=c_add.id, score=0.48, state=MasteryState.DEVELOPING))
    
    base_t = datetime.now(timezone.utc)
    mon = ClassSession(classroom_id=c.id, target_competency_id=c_add.id, duration_minutes=45, status=SessionStatus.COMPLETED, date=base_t - timedelta(days=5))
    thu = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45, status=SessionStatus.ATTENDANCE_RECORDED, date=base_t)
    db_session.add_all([mon, thu])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=raj.id, class_session_id=mon.id, status=AttendanceStatus.ABSENT))
    db_session.add(AttendanceRecord(student_id=raj.id, class_session_id=thu.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{thu.id}/groups/generate", json={})
    assert res.status_code == 200
    groups = res.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["group_type"] == "recovery"
    assert groups[0]["focus_competency"]["name"] == "Two-digit addition"
    assert groups[0]["students"][0]["name"] == "Rajkumar"
    assert thu.status == SessionStatus.GROUPED

def test_aditi_extension_subtraction(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"NUM_ADD_2D{uuid.uuid4()}", subject="math", name="Two-digit addition")
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    aditi = Student(classroom_id=c.id, name="Aditi", grade=2)
    db_session.add_all([c_add, c_sub, aditi])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    
    db_session.add(StudentMastery(student_id=aditi.id, competency_id=c_add.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=aditi.id, competency_id=c_sub.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    base_t = datetime.now(timezone.utc)
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45, status=SessionStatus.DRAFT, date=base_t)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=aditi.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "extension"
    assert groups[0]["focus_competency"]["name"] == "Two-digit subtraction"

def test_kiran_check_addition_assessment(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"NUM_ADD_2D{uuid.uuid4()}", subject="math", name="Two-digit addition")
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    s = Student(classroom_id=c.id, name="Kiran", grade=2)
    db_session.add_all([c_add, c_sub, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "check"
    assert "Assessment" not in groups[0]["name"] # DB doesn't save mode in name except as Check
    # but the assignment reason will mention assessment
    assert "assessment" in groups[0]["students"][0]["assignment_reason"]

def test_developing_prerequisite_quick_check(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"NUM_ADD_2D{uuid.uuid4()}", subject="math", name="Two-digit addition")
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_add, c_sub, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_add.id, score=0.60, state=MasteryState.DEVELOPING))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "check"
    assert "quick check" in groups[0]["students"][0]["assignment_reason"]

def test_target_missing_guided(client, db_session):
    c = setup_base(db_session)
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_sub, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "guided"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.90
    assert m_res["target_mastery_state"] == "unknown"

def test_target_lt_0_40_guided(client, db_session):
    c = setup_base(db_session)
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_sub, s])
    db_session.commit()
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_sub.id, score=0.30, state=MasteryState.NEEDS_SUPPORT))
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "guided"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.90
    assert m_res["target_mastery_state"] == "unknown"

def test_target_between_40_70_practice(client, db_session):
    c = setup_base(db_session)
    c_sub = Competency(code=f"NUM_SUB_2D{uuid.uuid4()}", subject="math", name="Two-digit subtraction")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_sub, s])
    db_session.commit()
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_sub.id, score=0.55, state=MasteryState.DEVELOPING))
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "practice"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.55
    assert m_res["target_mastery_source"] == "historical_evidence"
    assert m_res["target_mastery_stale"] == False

def test_no_prerequisite_target_practice(client, db_session):
    # Tests that when there are no prerequisites at all, logic correctly picks target mastery
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_t.id, score=0.60, state=MasteryState.DEVELOPING))
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "practice"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.55
    assert m_res["target_mastery_source"] == "historical_evidence"
    assert m_res["target_mastery_stale"] == False

def test_cross_grade_same_need_grouping(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=3)
    db_session.add_all([c_add, c_sub, s1, s2])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert len(groups) == 1
    assert groups[0]["student_count"] == 2
    assert groups[0]["grade_distribution"]["1"] == 1
    assert groups[0]["grade_distribution"]["3"] == 1

def test_same_grade_different_need_separation(client, db_session):
    c = setup_base(db_session)
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    s1 = Student(classroom_id=c.id, name="S1", grade=2)
    s2 = Student(classroom_id=c.id, name="S2", grade=2)
    db_session.add_all([c_add, c_sub, s1, s2])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    
    # s2 has both
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_add.id, score=0.9, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_sub.id, score=0.9, state=MasteryState.MASTERED))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert len(groups) == 2
    assert set([g["group_type"] for g in groups]) == {"check", "extension"}

def test_absent_excluded(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.ABSENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert len(res.json()["groups"]) == 0
    assert res.json()["excluded_students"][0]["student_id"] == str(s.id)

def test_late_included(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.LATE))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert len(res.json()["groups"]) == 1

def test_missing_attendance_blocks_generation(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=2)
    s2 = Student(classroom_id=c.id, name="S2", grade=2)
    db_session.add_all([c_t, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 409
    assert res.json()["detail"] == "Not all active students have attendance recorded."
    assert res.json()["error_code"] == "ATTENDANCE_INCOMPLETE"

def test_inactive_excluded(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=2, active=False)
    s2 = Student(classroom_id=c.id, name="S2", grade=2)
    db_session.add_all([c_t, s, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    # Note: we didn't add attendance for s, but since s is inactive, it shouldn't block generation
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200
    assert res.json()["summary"]["active_students"] == 1
    assert len(res.json()["groups"][0]["students"]) == 1
    assert res.json()["groups"][0]["students"][0]["student_id"] == str(s2.id)

def test_every_eligible_student_exactly_once(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=2)
    s2 = Student(classroom_id=c.id, name="S2", grade=2)
    db_session.add_all([c_t, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.LATE))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    
    mems = db_session.query(GroupMembership).filter_by(session_id=sess.id).all()
    # s1 and s2 exactly once
    assert len(mems) == 2
    student_ids = [str(m.student_id) for m in mems]
    assert set(student_ids) == {str(s1.id), str(s2.id)}

def test_no_duplicate_membership(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=2)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.PRACTICE, reason="x")
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.PRACTICE, reason="y")
    db_session.add_all([g1, g2])
    db_session.commit()
    
    # DB test
    import sqlalchemy.exc
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s.id, assignment_reason="x"))
    db_session.commit()
    
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s.id, assignment_reason="y"))
        db_session.commit()

def test_practice_extension_compression(client, db_session):
    # Classroom max_groups is 4
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    c_d = Competency(code=f"D{uuid.uuid4()}", subject="math", name="D")
    c_e = Competency(code=f"E{uuid.uuid4()}", subject="math", name="E")
    
    # 5 students, each needing a different group:
    # S1: Recovery A
    # S2: Recovery B
    # S3: Recovery C
    # S4: Practice Target
    # S5: Extension Target
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    s3 = Student(classroom_id=c.id, name="S3", grade=1)
    s4 = Student(classroom_id=c.id, name="S4", grade=1)
    s5 = Student(classroom_id=c.id, name="S5", grade=1)
    db_session.add_all([c_a, c_b, c_c, c_d, c_e, s1, s2, s3, s4, s5])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_c.id))
    db_session.commit()
    
    # Setup masteries for gaps
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_a.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_b.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_c.id, score=0.90, state=MasteryState.MASTERED))
    
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_b.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_c.id, score=0.90, state=MasteryState.MASTERED))
    
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_b.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_c.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    
    # S4 (practice) and S5 (extension) have prereqs mastered
    for st in [s4, s5]:
        db_session.add(StudentMastery(student_id=st.id, competency_id=c_a.id, score=0.90, state=MasteryState.MASTERED))
        db_session.add(StudentMastery(student_id=st.id, competency_id=c_b.id, score=0.90, state=MasteryState.MASTERED))
        db_session.add(StudentMastery(student_id=st.id, competency_id=c_c.id, score=0.90, state=MasteryState.MASTERED))
        
    db_session.add(StudentMastery(student_id=s4.id, competency_id=c_d.id, score=0.55, state=MasteryState.DEVELOPING))
    db_session.add(StudentMastery(student_id=s5.id, competency_id=c_d.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_d.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    for st in [s1, s2, s3, s4, s5]:
        db_session.add(AttendanceRecord(student_id=st.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    data = res.json()
    assert data["summary"]["groups_created"] == 4
    assert data["summary"]["compressed"] == True
    
    groups = data["groups"]
    pg = next(g for g in groups if g["group_type"] == "practice")
    assert pg["mixed_needs"] == True
    assert pg["student_count"] == 2
    student_ids = [s["student_id"] for s in pg["students"]]
    assert str(s4.id) in student_ids
    assert str(s5.id) in student_ids
    assert not any(g["group_type"] == "extension" for g in groups)

def test_guided_practice_compression(client, db_session):
    # Setup needs 5 groups: Recovery A, Recovery B, Recovery C, Guided, Practice
    # Should compress Practice into Guided
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    c_d = Competency(code=f"D{uuid.uuid4()}", subject="math", name="D")
    
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    s3 = Student(classroom_id=c.id, name="S3", grade=1)
    s4 = Student(classroom_id=c.id, name="S4", grade=1)
    s5 = Student(classroom_id=c.id, name="S5", grade=1)
    db_session.add_all([c_a, c_b, c_c, c_d, s1, s2, s3, s4, s5])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_c.id))
    db_session.commit()
    
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_a.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_b.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_c.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    # Give s1-s3 mastery for the others
    for st, bad_c in [(s1, c_a), (s2, c_b), (s3, c_c)]:
        for other_c in [c_a, c_b, c_c]:
            if other_c != bad_c:
                db_session.add(StudentMastery(student_id=st.id, competency_id=other_c.id, score=0.90, state=MasteryState.MASTERED))
                
    # S4 (guided: no target mastery), S5 (practice: 0.55 target mastery)
    for st in [s4, s5]:
        for prereq in [c_a, c_b, c_c]:
            db_session.add(StudentMastery(student_id=st.id, competency_id=prereq.id, score=0.90, state=MasteryState.MASTERED))
            
    db_session.add(StudentMastery(student_id=s5.id, competency_id=c_d.id, score=0.55, state=MasteryState.DEVELOPING))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_d.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    for st in [s1, s2, s3, s4, s5]:
        db_session.add(AttendanceRecord(student_id=st.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    data = res.json()
    groups = data["groups"]
    assert len(groups) == 4
    gg = next(g for g in groups if g["group_type"] == "guided")
    assert gg["mixed_needs"] == True
    assert gg["student_count"] == 2
    assert not any(g["group_type"] == "practice" for g in groups)

def test_check_recovery_same_focus_compression(client, db_session):
    # Need 5 groups to trigger compression: Recovery A, Check A, Recovery B, Recovery C, Guided Target
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_c = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C")
    c_d = Competency(code=f"D{uuid.uuid4()}", subject="math", name="D")
    
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    s3 = Student(classroom_id=c.id, name="S3", grade=1)
    s4 = Student(classroom_id=c.id, name="S4", grade=1)
    s5 = Student(classroom_id=c.id, name="S5", grade=1)
    db_session.add_all([c_a, c_b, c_c, c_d, s1, s2, s3, s4, s5])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_d.id, prerequisite_competency_id=c_c.id))
    db_session.commit()
    
    # S1 Recovery A
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_a.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    # S2 Check A (missing mastery = INSUFFICIENT_EVIDENCE)
    
    # S3 Recovery B
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_b.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    
    # S4 Recovery C
    db_session.add(StudentMastery(student_id=s4.id, competency_id=c_c.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    
    # S5 Guided (all prereqs mastered)
    for prereq in [c_a, c_b, c_c]:
        db_session.add(StudentMastery(student_id=s1.id, competency_id=prereq.id, score=0.90, state=MasteryState.MASTERED)) if prereq != c_a else None
        db_session.add(StudentMastery(student_id=s2.id, competency_id=prereq.id, score=0.90, state=MasteryState.MASTERED)) if prereq != c_a else None
        db_session.add(StudentMastery(student_id=s3.id, competency_id=prereq.id, score=0.90, state=MasteryState.MASTERED)) if prereq != c_b else None
        db_session.add(StudentMastery(student_id=s4.id, competency_id=prereq.id, score=0.90, state=MasteryState.MASTERED)) if prereq != c_c else None
        db_session.add(StudentMastery(student_id=s5.id, competency_id=prereq.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_d.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    for st in [s1, s2, s3, s4, s5]:
        db_session.add(AttendanceRecord(student_id=st.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    data = res.json()
    assert data["summary"]["groups_created"] == 4
    
    rg = next(g for g in data["groups"] if g["group_type"] == "recovery" and g["focus_competency"]["id"] == str(c_a.id))
    assert rg["mixed_needs"] == True
    assert rg["student_count"] == 2
    student_ids = [s["student_id"] for s in rg["students"]]
    assert str(s1.id) in student_ids
    assert str(s2.id) in student_ids
    
    s2_member = next(s for s in rg["students"] if s["student_id"] == str(s2.id))
    assert "Requires assessment" in s2_member["assignment_reason"]
    
def test_mixed_support_fallback(client, db_session):
    # Need 6 groups of Recovery/Check, no target groups
    c = setup_base(db_session)
    comps = [Competency(code=f"C{i}{uuid.uuid4()}", subject="math", name=f"C{i}") for i in range(6)]
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    students = [Student(classroom_id=c.id, name=f"S{i}", grade=1) for i in range(6)]
    db_session.add_all(comps + [c_t] + students)
    db_session.commit()
    
    for comp in comps:
        db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=comp.id))
    db_session.commit()
    
    for i in range(6):
        db_session.add(StudentMastery(student_id=students[i].id, competency_id=comps[i].id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
        for j in range(6):
            if i != j:
                db_session.add(StudentMastery(student_id=students[i].id, competency_id=comps[j].id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    for st in students:
        db_session.add(AttendanceRecord(student_id=st.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    data = res.json()
    assert data["summary"]["groups_created"] == 4
    mixed = next((g for g in data["groups"] if g["group_type"] == "mixed_support"), None)
    assert mixed is not None
    assert mixed["mixed_needs"] == True
    # since there are 6 groups and 4 max, 3 of them should be merged into 1 mixed support
    assert mixed["student_count"] == 3

def test_manual_move_and_regeneration_conflict(client, db_session):
    c = setup_base(db_session)
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([c_sub, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_sub.id, score=0.30, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_sub.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200
    groups = res.json()["groups"]
    g_guided = next(g for g in groups if g["group_type"] == "guided")
    g_ext = next(g for g in groups if g["group_type"] == "extension")
    
    # move s1 to extension
    res_move = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s1.id),
        "target_group_id": g_ext["id"],
        "reason": "Teacher override"
    })
    assert res_move.status_code == 200
    # verify teacher_modified on DB
    g1 = db_session.query(LearningGroup).filter_by(id=g_guided["id"]).first()
    g2 = db_session.query(LearningGroup).filter_by(id=g_ext["id"]).first()
    assert g1.teacher_modified == True
    assert g2.teacher_modified == True
    
    # attempt regenerate
    res_regen = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True})
    assert res_regen.status_code == 409
    assert res_regen.json()["error_code"] == "CONFLICT"
    
    res_force = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True, "force_replace_teacher_edits": True})
    assert res_force.status_code == 200

def test_cross_session_protection(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    sess1 = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    sess2 = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add_all([sess1, sess2])
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess1.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess2.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res1 = client.post(f"/api/v1/sessions/{sess1.id}/groups/generate", json={}).json()
    res2 = client.post(f"/api/v1/sessions/{sess2.id}/groups/generate", json={}).json()
    
    g2_id = res2["groups"][0]["id"]
    
    # try move s from sess1 to g2 in sess2
    res_move = client.post(f"/api/v1/sessions/{sess1.id}/groups/move-student", json={
        "student_id": str(s.id),
        "target_group_id": g2_id
    })
    assert res_move.status_code == 400
    assert res_move.json()["error_code"] == "VALIDATION_ERROR"
    assert "Target group invalid" in res_move.json()["detail"]

def test_atomic_rollback(client, db_session):
    import uuid
    from sqlalchemy.orm import Session
    from unittest.mock import patch
    import app.services.grouping_service as gs
    
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([c_t, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    # We will patch GroupMembership to raise an exception on the 2nd call
    call_count = [0]
    original_mem = gs.GroupMembership
    def mock_membership(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 2:
            raise Exception("Mock Membership Failure")
        return original_mem(*args, **kwargs)
        
    with patch("app.services.grouping_service.GroupMembership", side_effect=mock_membership):
        res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
        
    assert res.status_code == 500
    
    groups = db_session.query(LearningGroup).filter_by(session_id=sess.id).all()
    mems = db_session.query(GroupMembership).filter_by(session_id=sess.id).all()
    assert len(groups) == 0
    assert len(mems) == 0
    
    db_session.refresh(sess)
    assert sess.status == SessionStatus.DRAFT

def test_replacement_rollback(client, db_session):
    import uuid
    from unittest.mock import patch
    import app.services.grouping_service as gs
    
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    db_session.add_all([c_t, s1])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    # Generate once successfully
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    old_groups = db_session.query(LearningGroup).filter_by(session_id=sess.id).all()
    assert len(old_groups) == 1
    
    # Fail on replace
    def mock_membership(*args, **kwargs):
        raise Exception("Mock Replace Failure")
        
    with patch("app.services.grouping_service.GroupMembership", side_effect=mock_membership):
        res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True})
        
    assert res.status_code == 500
    
    # Old groups should remain intact!
    db_session.refresh(sess)
    assert sess.status == SessionStatus.GROUPED
    
    new_groups = db_session.query(LearningGroup).filter_by(session_id=sess.id).all()
    assert len(new_groups) == 1
    assert new_groups[0].id == old_groups[0].id
    
    new_mems = db_session.query(GroupMembership).filter_by(session_id=sess.id).all()
    assert len(new_mems) == 1
    assert new_mems[0].student_id == s1.id
    assert new_mems[0].group_id == old_groups[0].id


def test_generate_groups_draft_status(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.DRAFT)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200

def test_generate_groups_attendance_recorded_status(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.ATTENDANCE_RECORDED)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200

def test_generate_groups_grouped_status(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.GROUPED)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True})
    assert res.status_code == 200

def test_generate_groups_scheduled_fails(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.SCHEDULED)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 400

def test_generate_groups_activities_ready_fails(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.ACTIVITIES_READY)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 400

def test_move_student_invalid_student(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    
    bad_id = uuid.uuid4()
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(bad_id),
        "target_group_id": str(uuid.uuid4())
    })
    assert res.status_code == 400

def test_get_groups(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    
    res = client.get(f"/api/v1/sessions/{sess.id}/groups")
    assert res.status_code == 200
    assert len(res.json()["groups"]) == 1

def test_replace_existing_required_if_grouped(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 409

def test_generate_without_target_competency(client, db_session):
    c = setup_base(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    # Session with no target competency
    sess = ClassSession(classroom_id=c.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200
    # Should default to GUIDED for target missing
    assert res.json()["groups"][0]["group_type"] == "guided"
    
def test_tiebreak_on_competency_code(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A_CODE{uuid.uuid4()}", subject="math", name="A")
    c_z = Competency(code=f"Z_CODE{uuid.uuid4()}", subject="math", name="Z")
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_z, c_t, s])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_z.id))
    db_session.commit()
    # Both have identical state and score, should tie-break by competency code
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_a.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_z.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.json()["groups"][0]["focus_competency"]["name"] == "A"


def test_update_group(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    
    res_get = client.get(f"/api/v1/sessions/{sess.id}/groups")
    g_id = res_get.json()["groups"][0]["id"]
    
    res_patch = client.patch(f"/api/v1/sessions/{sess.id}/groups/{g_id}", json={
        "name": "Custom Name",
        "reason": "Custom Reason"
    })
    assert res_patch.status_code == 200
    
    res_check = client.get(f"/api/v1/sessions/{sess.id}/groups")
    updated_g = res_check.json()["groups"][0]
    assert updated_g["name"] == "Custom Name"
    assert updated_g["reason"] == "Custom Reason"


def test_db_uniqueness_constraint(db_session):
    import sqlalchemy.exc
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.GUIDED, reason="r")
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.PRACTICE, reason="r2")
    db_session.add_all([g1, g2])
    db_session.commit()
    
    # First membership succeeds
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s.id, assignment_reason="r"))
    db_session.commit()
    
    # Second membership for the same student in the same session must fail
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s.id, assignment_reason="r2"))
        db_session.commit()
    db_session.rollback()

def test_unsatisfiable_capacity(client, db_session):
    # Setup a scenario that requires more than 1 group but max_groups is 1
    c = setup_base(db_session)
    c.max_groups = 1
    db_session.commit()
    
    c_sub = Competency(code=f"SUB{uuid.uuid4()}", subject="math", name="SUB")
    c_add = Competency(code=f"ADD{uuid.uuid4()}", subject="math", name="ADD")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    s3 = Student(classroom_id=c.id, name="S3", grade=1)
    db_session.add_all([c_sub, c_add, s1, s2, s3])
    db_session.commit()
    
    db_session.add(CompetencyPrerequisite(competency_id=c_sub.id, prerequisite_competency_id=c_add.id))
    db_session.commit()
    
    # S1 Needs Recovery Addition (Needs Support)
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_add.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    # S2 Ready for Guided Subtraction
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_add.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_sub.id, score=0.20, state=MasteryState.NEEDS_SUPPORT))
    # S3 Ready for Extension Subtraction
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_add.id, score=0.90, state=MasteryState.MASTERED))
    db_session.add(StudentMastery(student_id=s3.id, competency_id=c_sub.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_sub.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    for st in [s1, s2, s3]:
        db_session.add(AttendanceRecord(student_id=st.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 409
    assert res.json()["error_code"] == "GROUP_CAPACITY_UNSATISFIABLE"
    
    db_session.refresh(sess)
    assert sess.status == SessionStatus.DRAFT
    

def test_stale_target_090_guided(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    # Add a stale mastery
    m = StudentMastery(student_id=s.id, competency_id=c_t.id, score=0.90, state=MasteryState.MASTERED)
    m.last_updated = datetime.now(timezone.utc) - timedelta(days=60)
    db_session.add(m)
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, date=datetime.now(timezone.utc))
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res.status_code == 200
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "guided"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.90
    assert m_res["target_mastery_state"] == "mastered"
    assert m_res["target_mastery_stale"] == True

def test_unknown_target_state_guided(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    # Explicit UNKNOWN state
    m = StudentMastery(student_id=s.id, competency_id=c_t.id, score=0.90, state=MasteryState.UNKNOWN)
    db_session.add(m)
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, date=datetime.now(timezone.utc))
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "guided"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.90
    assert m_res["target_mastery_state"] == "unknown"

def test_fresh_target_090_extension(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    m = StudentMastery(student_id=s.id, competency_id=c_t.id, score=0.90, state=MasteryState.MASTERED)
    db_session.add(m)
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, date=datetime.now(timezone.utc))
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "extension"

def test_historical_valid_target_055_practice(client, db_session):
    from app.models.all_models import MasteryEvidence
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    # Provide valid historical evidence
    e = MasteryEvidence(student_id=s.id, competency_id=c_t.id, source_type=EvidenceSource.MANUAL_ASSESSMENT, score=0.55, created_at=datetime.now(timezone.utc) - timedelta(days=2))
    db_session.add(e)
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, date=datetime.now(timezone.utc))
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups = res.json()["groups"]
    assert groups[0]["group_type"] == "practice"
    m_res = groups[0]["students"][0]
    assert m_res["target_mastery_score"] == 0.55
    assert m_res["target_mastery_source"] == "historical_evidence"
    assert m_res["target_mastery_stale"] == False

def test_manual_move_marks_group_and_session(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([c_t, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    # Give them different masteries so they end up in different groups
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_t.id, score=0.30, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_t.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups_req = client.get(f"/api/v1/sessions/{sess.id}/groups").json()["groups"]
    g_g = next(g for g in groups_req if g["group_type"] == "guided")
    g_e = next(g for g in groups_req if g["group_type"] == "extension")
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s1.id),
        "target_group_id": g_e["id"],
        "reason": "Because"
    })
    
    db_session.refresh(sess)
    assert sess.groups_teacher_modified == True
    
    g_db = db_session.query(LearningGroup).filter_by(id=g_e["id"]).first()
    assert g_db.teacher_modified == True
    
    # Source group (guided) should be deleted because it's empty
    g_s_db = db_session.query(LearningGroup).filter_by(id=g_g["id"]).first()
    assert g_s_db is None

def test_same_group_move_idempotent(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    g_id = client.get(f"/api/v1/sessions/{sess.id}/groups").json()["groups"][0]["id"]
    
    # Move to same group
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s.id),
        "target_group_id": g_id
    })
    
    db_session.refresh(sess)
    assert sess.groups_teacher_modified == False
    g_db = db_session.query(LearningGroup).filter_by(id=g_id).first()
    assert g_db.teacher_modified == False

def test_assignment_reason_preserved_after_move(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([c_t, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_t.id, score=0.30, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_t.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    groups_req = client.get(f"/api/v1/sessions/{sess.id}/groups").json()["groups"]
    
    s1_member_orig = groups_req[0]["students"][0] if groups_req[0]["students"][0]["student_id"] == str(s1.id) else groups_req[1]["students"][0]
    orig_reason = s1_member_orig["assignment_reason"]
    
    g_e = next(g for g in groups_req if g["group_type"] == "extension")
    
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s1.id),
        "target_group_id": g_e["id"],
        "reason": "Teacher says so"
    })
    
    updated_groups = res.json()["groups"]
    g_ext_updated = next(g for g in updated_groups if g["id"] == g_e["id"])
    s1_member_updated = next(m for m in g_ext_updated["students"] if m["student_id"] == str(s1.id))
    
    assert s1_member_updated["assignment_reason"] == orig_reason
    assert s1_member_updated["teacher_override_reason"] == "Teacher says so"

def test_forced_regeneration_clears_modifications(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([c_t, s1, s2])
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(StudentMastery(student_id=s1.id, competency_id=c_t.id, score=0.30, state=MasteryState.NEEDS_SUPPORT))
    db_session.add(StudentMastery(student_id=s2.id, competency_id=c_t.id, score=0.90, state=MasteryState.MASTERED))
    db_session.commit()
    
    # Generate once
    client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    
    # Teacher moves student (modifies groups)
    groups_req = client.get(f"/api/v1/sessions/{sess.id}/groups").json()["groups"]
    g_e = next(g for g in groups_req if g["group_type"] == "extension")
    client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s1.id), "target_group_id": g_e["id"], "reason": "moved"
    })
    
    # Attempt regen without force - should 409
    res = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True})
    assert res.status_code == 409
    
    # Attempt force regen
    res_force = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True, "force_replace_teacher_edits": True})
    assert res_force.status_code == 200
    
    db_session.refresh(sess)
    assert sess.groups_teacher_modified == False
    
    new_db_groups = db_session.query(LearningGroup).filter_by(session_id=sess.id).all()
    for g in new_db_groups:
        assert g.teacher_modified == False
        
    new_mems = db_session.query(GroupMembership).filter_by(session_id=sess.id).all()
    for m in new_mems:
        assert m.teacher_override_reason is None


def test_generated_memberships_match_session_id(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_t, s])
    db_session.commit()
    
    sess1 = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess1)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess1.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess1.id}/groups/generate", json={})
    
    mems = db_session.query(GroupMembership).filter_by(session_id=sess1.id).all()
    for mem in mems:
        assert mem.session_id == mem.group.session_id
        assert mem.session_id == sess1.id
