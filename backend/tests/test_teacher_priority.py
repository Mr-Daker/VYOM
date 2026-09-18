import pytest
import uuid
from datetime import datetime, timezone, timedelta
from app.models.all_models import (
    Classroom, Student, Competency, ClassSession, AttendanceRecord,
    StudentMastery, CompetencyPrerequisite, MasteryEvidence, LearningGroup, GroupMembership, GroupPriority, User
)
from app.models.enums import AttendanceStatus, MasteryState, SessionStatus, GroupType, CheckMode, UserRole
from app.services.teacher_priority_service import TeacherPriorityService, select_top_factor
import app.core.priority_config as config
from sqlalchemy.exc import IntegrityError
from unittest.mock import patch

CURRENT = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)

def setup_base(db):
    u = User(name="Teacher", email=f"teacher-{uuid.uuid4()}@example.com", password_hash="test", role=UserRole.TEACHER)
    db.add(u)
    db.flush()
    c = Classroom(teacher_id=u.id, name="Class 1", max_groups=4)
    db.add(c)
    db.commit()
    return c

def setup_session_with_groups(db, c, dt=CURRENT, status=SessionStatus.GROUPED):
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    db.add(c_t)
    db.commit()
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=status, date=dt)
    db.add(sess)
    db.commit()
    return sess, c_t

def setup_historical_session(db, c, comp_id, dt, student_id, present=True):
    sess = ClassSession(classroom_id=c.id, target_competency_id=comp_id, duration_minutes=45, status=SessionStatus.COMPLETED, date=dt)
    db.add(sess)
    db.commit()
    db.add(AttendanceRecord(student_id=student_id, class_session_id=sess.id, status=AttendanceStatus.PRESENT if present else AttendanceStatus.ABSENT))
    db.commit()
    return sess

def test_config_validation_complete():
    orig = dict(config.PRIORITY_WEIGHTS)
    try:
        config.PRIORITY_WEIGHTS["instructional_need"] = 0
        with pytest.raises(ValueError, match="sum to 100"):
            config.validate_priority_config()
    finally:
        config.PRIORITY_WEIGHTS.update(orig)
        
    orig_val = config.INSTRUCTIONAL_NEED_VALUES["recovery"]
    try:
        config.INSTRUCTIONAL_NEED_VALUES["recovery"] = -0.1
        with pytest.raises(ValueError, match="between 0 and 1"):
            config.validate_priority_config()
    finally:
        config.INSTRUCTIONAL_NEED_VALUES["recovery"] = orig_val

    try:
        config.INSTRUCTIONAL_NEED_VALUES["recovery"] = 1.1
        with pytest.raises(ValueError, match="between 0 and 1"):
            config.validate_priority_config()
    finally:
        config.INSTRUCTIONAL_NEED_VALUES["recovery"] = orig_val
        
    orig_ref = config.PRIORITY_REFERENCE_GROUP_SIZE
    try:
        config.PRIORITY_REFERENCE_GROUP_SIZE = 0
        with pytest.raises(ValueError, match="must be > 0"):
            config.validate_priority_config()
        config.PRIORITY_REFERENCE_GROUP_SIZE = -1
        with pytest.raises(ValueError, match="must be > 0"):
            config.validate_priority_config()
    finally:
        config.PRIORITY_REFERENCE_GROUP_SIZE = orig_ref
        
    orig_t = dict(config.PRIORITY_TIER_THRESHOLDS)
    try:
        config.PRIORITY_TIER_THRESHOLDS["urgent"] = 70
        config.PRIORITY_TIER_THRESHOLDS["high"] = 70
        with pytest.raises(ValueError, match="strictly ordered"):
            config.validate_priority_config()
    finally:
        config.PRIORITY_TIER_THRESHOLDS.update(orig_t)
        
    try:
        config.PRIORITY_TIER_THRESHOLDS["urgent"] = 40
        config.PRIORITY_TIER_THRESHOLDS["high"] = 50
        with pytest.raises(ValueError, match="strictly ordered"):
            config.validate_priority_config()
    finally:
        config.PRIORITY_TIER_THRESHOLDS.update(orig_t)

    try:
        config.PRIORITY_TIER_THRESHOLDS["low"] = -10
        with pytest.raises(ValueError, match="between 0 and 100"):
            config.validate_priority_config()
    finally:
        config.PRIORITY_TIER_THRESHOLDS.update(orig_t)
        
    try:
        config.PRIORITY_TIER_THRESHOLDS["urgent"] = 105
        with pytest.raises(ValueError, match="between 0 and 100"):
            config.validate_priority_config()
    finally:
        config.PRIORITY_TIER_THRESHOLDS.update(orig_t)

def test_tier_boundaries():
    assert config.get_tier_for_score(70.00) == "urgent"
    assert config.get_tier_for_score(69.99) == "high"
    assert config.get_tier_for_score(50.00) == "high"
    assert config.get_tier_for_score(49.99) == "moderate"
    assert config.get_tier_for_score(30.00) == "moderate"
    assert config.get_tier_for_score(29.99) == "low"

def test_invalid_session_state(client, db_session):
    c = setup_base(db_session)
    sess, _ = setup_session_with_groups(db_session, c, status=SessionStatus.DRAFT)
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_SESSION_STATE"

def test_no_groups(client, db_session):
    c = setup_base(db_session)
    sess, _ = setup_session_with_groups(db_session, c)
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "NO_GROUPS"

def test_empty_group_rejected(client, db_session):
    c = setup_base(db_session)
    sess, _ = setup_session_with_groups(db_session, c)
    g = LearningGroup(session_id=sess.id, name="Empty", group_type=GroupType.EXTENSION, sort_order=0)
    db_session.add(g)
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PRIORITY_INVALID_GROUPING"

def test_score_arithmetic_and_bounds(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.commit()
    g = LearningGroup(session_id=sess.id, name="Prac", group_type=GroupType.PRACTICE, sort_order=0)
    db_session.add(g)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, original_group_type=GroupType.PRACTICE.value, assignment_reason="Prac"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    assert res.status_code == 200
    p = res.json()["priorities"][0]
    
    assert 0 <= p["priority_score"] <= 100
    total = sum(fb["contribution"] for fb in p["factor_breakdown"].values())
    assert abs(p["priority_score"] - total) < 0.01

def test_small_severe_recovery_vs_huge_extension(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    
    c_p = Competency(code=f"P{uuid.uuid4()}", subject="math", name="P")
    db_session.add(c_p)
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_p.id))
    
    # 2 Recovery (Confirmed Gap)
    g_r = LearningGroup(session_id=sess.id, name="Rec", group_type=GroupType.RECOVERY, focus_competency_id=c_p.id, sort_order=0)
    db_session.add(g_r)
    db_session.flush()
    for i in range(2):
        s = Student(classroom_id=c.id, name=f"R{i}", grade=1)
        db_session.add(s)
        db_session.commit()
        db_session.add(StudentMastery(student_id=s.id, competency_id=c_p.id, score=0.1, state=MasteryState.NEEDS_SUPPORT, last_updated=CURRENT-timedelta(days=1)))
        db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
        db_session.add(GroupMembership(session_id=sess.id, group_id=g_r.id, student_id=s.id, focus_competency_id=c_p.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    
    # 12 Extension (Mastered target)
    g_e = LearningGroup(session_id=sess.id, name="Ext", group_type=GroupType.EXTENSION, focus_competency_id=c_t.id, sort_order=1)
    db_session.add(g_e)
    db_session.flush()
    for i in range(12):
        s = Student(classroom_id=c.id, name=f"E{i}", grade=1)
        db_session.add(s)
        db_session.commit()
        db_session.add(StudentMastery(student_id=s.id, competency_id=c_t.id, score=0.9, state=MasteryState.MASTERED, last_updated=CURRENT-timedelta(days=1)))
        db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
        db_session.add(GroupMembership(session_id=sess.id, group_id=g_e.id, student_id=s.id, focus_competency_id=c_t.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    ps = res.json()["priorities"]
    assert ps[0]["group_type"] == "recovery"
    assert ps[1]["group_type"] == "extension"
    assert ps[0]["priority_score"] > ps[1]["priority_score"]

def test_check_can_outrank_recovery(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    c_p = Competency(code=f"P{uuid.uuid4()}", subject="math", name="P")
    db_session.add(c_p)
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_p.id))
    
    # 1 Recovery (Confirmed Gap, score=0.20, no missed sessions)
    g_r = LearningGroup(session_id=sess.id, name="Rec", group_type=GroupType.RECOVERY, focus_competency_id=c_p.id, sort_order=1)
    db_session.add(g_r)
    db_session.flush()
    s_r = Student(classroom_id=c.id, name="R", grade=1)
    db_session.add(s_r)
    db_session.commit()
    db_session.add(StudentMastery(student_id=s_r.id, competency_id=c_p.id, score=0.20, state=MasteryState.NEEDS_SUPPORT, last_updated=CURRENT-timedelta(days=1)))
    db_session.add(AttendanceRecord(student_id=s_r.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g_r.id, student_id=s_r.id, focus_competency_id=c_p.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    
    # 8 Check (Insufficient Evidence -> Assessment required, no missed sessions)
    g_c = LearningGroup(session_id=sess.id, name="Chk", group_type=GroupType.CHECK, focus_competency_id=c_p.id, check_mode=CheckMode.ASSESSMENT, sort_order=0)
    db_session.add(g_c)
    db_session.flush()
    for i in range(8):
        s = Student(classroom_id=c.id, name=f"C{i}", grade=1)
        db_session.add(s)
        db_session.commit()
        db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
        # No MasteryEvidence or StudentMastery to force INSUFFICIENT_EVIDENCE
        db_session.add(GroupMembership(session_id=sess.id, group_id=g_c.id, student_id=s.id, focus_competency_id=c_p.id, original_group_type=GroupType.CHECK.value, original_check_mode=CheckMode.ASSESSMENT.value, assignment_reason="Chk"))
        
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    ps = res.json()["priorities"]
    assert ps[0]["group_type"] == "check"
    assert ps[1]["group_type"] == "recovery"
    
    # Check > Recovery score explicitly
    assert ps[0]["priority_score"] > ps[1]["priority_score"]
    
    # Check Math (35 * 0.85 = 29.75; 25 * 0.65 = 16.25; 15 * 1.0 = 15; 5 * 1.0 = 5 => 66.0)
    assert abs(ps[0]["priority_score"] - 66.0) < 0.1
    # Rec Math (35 * 1.0 = 35; 25 * 1.0 = 25; reach = 5 * 0.125 = 0.625 => ~60.62)
    assert abs(ps[1]["priority_score"] - 60.62) < 0.1

def test_deterministic_regeneration(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([s1, s2])
    g1 = LearningGroup(session_id=sess.id, name="Ext", group_type=GroupType.EXTENSION, sort_order=0)
    g2 = LearningGroup(session_id=sess.id, name="Rec", group_type=GroupType.RECOVERY, sort_order=1)
    db_session.add_all([g1, g2])
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s2.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    db_session.commit()
    
    r1 = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={}).json()
    r2 = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={"replace_existing": True}).json()
    
    def clean(p_list):
        for p in p_list:
            del p["group_id"]
        return p_list
        
    assert clean(r1["priorities"]) == clean(r2["priorities"])

def test_score_rank_tie_breaking(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([s1, s2])
    g1 = LearningGroup(session_id=sess.id, name="E1", group_type=GroupType.EXTENSION, sort_order=2)
    g2 = LearningGroup(session_id=sess.id, name="E2", group_type=GroupType.EXTENSION, sort_order=1)
    db_session.add_all([g1, g2])
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="E1"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s2.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="E2"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    ps = res.json()["priorities"]
    assert ps[0]["group_name"] == "E2"
    
    g2.sort_order = 2
    db_session.commit()
    res2 = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={"replace_existing": True})
    ps2 = res2.json()["priorities"]
    
    expected_order = sorted([g1, g2], key=lambda x: str(x.id))
    assert ps2[0]["group_id"] == str(expected_order[0].id)
    assert ps2[1]["group_id"] == str(expected_order[1].id)

def test_top_reason_tie_breaking():
    # Unit test the actual pure helper
    c1 = {
        "instructional_need": 10.0,
        "evidence_severity": 10.0,
        "uncertainty": 5.0,
        "missed_instruction": 0.0,
        "group_complexity": 0.0,
        "reach": 0.0,
    }
    assert select_top_factor(c1) == "instructional_need"
    
    c2 = {
        "instructional_need": 0.0,
        "evidence_severity": 0.0,
        "uncertainty": 8.0,
        "missed_instruction": 0.0,
        "group_complexity": 8.0,
        "reach": 0.0,
    }
    assert select_top_factor(c2) == "uncertainty"
    
    c3 = {
        "instructional_need": 0.0,
        "evidence_severity": 0.0,
        "uncertainty": 0.0,
        "missed_instruction": 0.0,
        "group_complexity": 0.0,
        "reach": 0.0,
    }
    assert select_top_factor(c3) is None

def test_missing_gap_evidence_fallback(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    c_p = Competency(code=f"P{uuid.uuid4()}", subject="math", name="P")
    db_session.add(c_p)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.commit()
    g = LearningGroup(session_id=sess.id, name="Rec", group_type=GroupType.RECOVERY, focus_competency_id=c_p.id, sort_order=0)
    db_session.add(g)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, focus_competency_id=c_p.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    p = res.json()["priorities"][0]
    
    assert p["factor_breakdown"]["evidence_severity"]["contribution"] == 0.0
    assert p["factor_breakdown"]["missed_instruction"]["contribution"] == 0.0
    assert any("Supporting direct-prerequisite evidence could not be resolved for 1 learner" in r for r in p["reasons"])

def test_mixed_support_complexity(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g = LearningGroup(session_id=sess.id, name="Mix", group_type=GroupType.MIXED_SUPPORT, sort_order=0)
    db_session.add(g)
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    db_session.add(s1)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s1.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    p = res.json()["priorities"][0]
    assert p["factor_breakdown"]["group_complexity"]["contribution"] == 10.0
    
def test_compressed_original_need(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g = LearningGroup(session_id=sess.id, name="Prac", group_type=GroupType.PRACTICE, sort_order=0)
    db_session.add(g)
    db_session.flush()
    for i in range(2):
        s = Student(classroom_id=c.id, name=f"P{i}", grade=1)
        db_session.add(s)
        db_session.flush()
        db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, original_group_type=GroupType.PRACTICE.value, assignment_reason="Prac"))
    for i in range(3):
        s = Student(classroom_id=c.id, name=f"E{i}", grade=1)
        db_session.add(s)
        db_session.flush()
        db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    p = res.json()["priorities"][0]
    avg_need = (2 * 0.30 + 3 * 0.05) / 5
    assert abs(p["factor_breakdown"]["instructional_need"]["raw"] - avg_need) < 0.01

def test_teacher_moved_learner_integration(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g_rec = LearningGroup(session_id=sess.id, name="Rec", group_type=GroupType.RECOVERY, sort_order=0)
    g_ext = LearningGroup(session_id=sess.id, name="Ext", group_type=GroupType.EXTENSION, sort_order=1)
    db_session.add_all([g_rec, g_ext])
    s_r = Student(classroom_id=c.id, name="S_R", grade=1)
    s_e = Student(classroom_id=c.id, name="S_E", grade=1)
    db_session.add_all([s_r, s_e])
    db_session.flush()
    
    db_session.add(AttendanceRecord(student_id=s_r.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s_e.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    
    db_session.add(GroupMembership(session_id=sess.id, group_id=g_rec.id, student_id=s_r.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g_ext.id, student_id=s_e.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    orig_res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={}).json()["priorities"]
    ext_orig_p = next(p for p in orig_res if p["group_id"] == str(g_ext.id))
    
    move_res = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s_r.id),
        "target_group_id": str(g_ext.id),
        "reason": "Teacher moved learner"
    })
    assert move_res.status_code == 200
    
    # Assert membership directly in DB
    mem_sr = db_session.query(GroupMembership).filter_by(session_id=sess.id, student_id=s_r.id).first()
    assert mem_sr.group_id == g_ext.id
    assert mem_sr.original_group_type == GroupType.RECOVERY.value
    
    db_session.refresh(sess)
    assert sess.priority_stale is True
    
    new_res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={"replace_existing": True}).json()["priorities"]
    ext_new_p = next(p for p in new_res if p["group_id"] == str(g_ext.id))
    
    assert ext_new_p["group_type"] == "extension"
    assert ext_new_p["factor_breakdown"]["instructional_need"]["raw"] > ext_orig_p["factor_breakdown"]["instructional_need"]["raw"]
    assert ext_new_p["priority_score"] > ext_orig_p["priority_score"]

def test_acceptance_rajkumar(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code="NUM_SUB_2D", subject="math", name="Sub")
    c_p = Competency(code="NUM_ADD_2D", subject="math", name="Add")
    db_session.add_all([c_t, c_p])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_p.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.GROUPED, date=CURRENT)
    s = Student(classroom_id=c.id, name="Rajkumar", grade=1)
    db_session.add_all([sess, s])
    db_session.commit()
    
    # Present current
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    
    # History
    mon = setup_historical_session(db_session, c, c_p.id, CURRENT - timedelta(days=3), s.id, True)
    tue = setup_historical_session(db_session, c, c_p.id, CURRENT - timedelta(days=2), s.id, False)
    wed = setup_historical_session(db_session, c, c_p.id, CURRENT - timedelta(days=1), s.id, False)
    
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_p.id, score=0.48, state=MasteryState.DEVELOPING, last_updated=CURRENT-timedelta(days=1)))
    
    g = LearningGroup(session_id=sess.id, name="Rec", group_type=GroupType.RECOVERY, focus_competency_id=c_p.id, sort_order=0)
    db_session.add(g)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, focus_competency_id=c_p.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    p = res.json()["priorities"][0]
    
    fb = p["factor_breakdown"]
    assert fb["instructional_need"]["raw"] == 1.0
    assert fb["evidence_severity"]["raw"] == 0.8
    assert abs(fb["missed_instruction"]["raw"] - (2/3)) < 0.01

def test_acceptance_aditi(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code="NUM_SUB_2D", subject="math", name="Sub")
    db_session.add(c_t)
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.GROUPED, date=CURRENT)
    s = Student(classroom_id=c.id, name="Aditi", grade=1)
    db_session.add_all([sess, s])
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(StudentMastery(student_id=s.id, competency_id=c_t.id, score=0.9, state=MasteryState.MASTERED, last_updated=CURRENT-timedelta(days=1)))
    
    g = LearningGroup(session_id=sess.id, name="Ext", group_type=GroupType.EXTENSION, focus_competency_id=c_t.id, sort_order=0)
    db_session.add(g)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, focus_competency_id=c_t.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    fb = res.json()["priorities"][0]["factor_breakdown"]
    
    assert fb["instructional_need"]["raw"] == 0.05
    assert fb["evidence_severity"]["raw"] == 0.0
    assert fb["uncertainty"]["raw"] == 0.0
    assert fb["missed_instruction"]["raw"] == 0.0

def test_acceptance_kiran(client, db_session):
    c = setup_base(db_session)
    c_t = Competency(code="NUM_SUB_2D", subject="math", name="Sub")
    c_p = Competency(code="NUM_ADD_2D", subject="math", name="Add")
    db_session.add_all([c_t, c_p])
    db_session.commit()
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_p.id))
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45, status=SessionStatus.GROUPED, date=CURRENT)
    s = Student(classroom_id=c.id, name="Kiran", grade=1)
    db_session.add_all([sess, s])
    db_session.commit()
    
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    # NO MasteryEvidence or StudentMastery to force INSUFFICIENT_EVIDENCE
    
    g = LearningGroup(session_id=sess.id, name="Chk", group_type=GroupType.CHECK, focus_competency_id=c_p.id, check_mode=CheckMode.ASSESSMENT, sort_order=0)
    db_session.add(g)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, focus_competency_id=c_p.id, original_group_type=GroupType.CHECK.value, original_check_mode=CheckMode.ASSESSMENT.value, assignment_reason="Chk"))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    fb = res.json()["priorities"][0]["factor_breakdown"]
    
    assert fb["instructional_need"]["raw"] == 0.85
    assert fb["evidence_severity"]["raw"] == 0.65
    assert fb["uncertainty"]["raw"] == 1.0

def test_get_persistence_and_snapshot_counts(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g = LearningGroup(session_id=sess.id, name="E1", group_type=GroupType.EXTENSION, sort_order=0)
    db_session.add(g)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.flush()
    mem = GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext")
    db_session.add(mem)
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    
    db_session.delete(mem)
    db_session.commit()
    
    res = client.get(f"/api/v1/sessions/{sess.id}/priorities").json()
    p = res["priorities"][0]
    
    assert p["student_count"] == 1
    assert p["current_student_count"] == 0

def test_manual_reorder_success(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.EXTENSION, sort_order=1)
    db_session.add_all([g1, g2])
    s1, s2 = Student(classroom_id=c.id, name="S1", grade=1), Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([s1, s2])
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s2.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    gen_res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    orig = gen_res.json()["priorities"]
    assert orig[0]["group_id"] == str(g1.id)
    assert orig[1]["group_id"] == str(g2.id)
    
    reorder_res = client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={
        "ordered_group_ids": [str(g2.id), str(g1.id)],
        "reason": "Teacher manual logic"
    }).json()["priorities"]
    
    assert reorder_res[0]["group_id"] == str(g2.id)
    assert reorder_res[0]["teacher_rank"] == 1
    assert reorder_res[0]["effective_rank"] == 1
    assert reorder_res[0]["priority_rank"] == 2
    assert reorder_res[0]["teacher_override_reason"] == "Teacher manual logic"
    
def test_reorder_validation(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    db_session.add(g1)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    
    r1 = client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": []})
    assert r1.status_code == 400
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"
    
    r2 = client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": [str(g1.id), str(g1.id)]})
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"
    
    sess.status = SessionStatus.SCHEDULED
    db_session.commit()
    r3 = client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": [str(g1.id)]})
    assert r3.status_code == 400
    assert r3.json()["error"]["code"] == "INVALID_SESSION_STATE"
    
def test_reorder_reason_clearing(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g = LearningGroup(session_id=sess.id, name="G", group_type=GroupType.EXTENSION, sort_order=0)
    db_session.add(g)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    
    client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": [str(g.id)], "reason": "X"})
    r2 = client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": [str(g.id)]})
    assert r2.json()["priorities"][0]["teacher_override_reason"] is None

def test_priority_stale_after_student_move(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.RECOVERY, sort_order=1)
    db_session.add_all([g1, g2])
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    s2 = Student(classroom_id=c.id, name="S2", grade=1)
    s3 = Student(classroom_id=c.id, name="S3", grade=1)
    db_session.add_all([s1, s2, s3])
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s2.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s3.id, original_group_type=GroupType.RECOVERY.value, assignment_reason="Rec"))
    
    db_session.add(AttendanceRecord(student_id=s1.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s2.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.add(AttendanceRecord(student_id=s3.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    
    move_res = client.post(f"/api/v1/sessions/{sess.id}/groups/move-student", json={
        "student_id": str(s1.id),
        "target_group_id": str(g2.id),
        "reason": "Moving student"
    })
    assert move_res.status_code == 200
    
    db_session.refresh(sess)
    assert sess.priority_stale is True
    
    get_res = client.get(f"/api/v1/sessions/{sess.id}/priorities")
    assert get_res.json()["stale"] is True
    
    r_reorder = client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": [str(g1.id), str(g2.id)]})
    assert r_reorder.status_code == 409
    assert r_reorder.json()["error"]["code"] == "PRIORITY_STALE"

def test_priority_stale_after_group_patch(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    db_session.add(g1)
    s1 = Student(classroom_id=c.id, name="S1", grade=1)
    db_session.add(s1)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    
    patch_res = client.patch(f"/api/v1/sessions/{sess.id}/groups/{g1.id}", json={"name": "Teacher Updated Group"})
    assert patch_res.status_code == 200
    db_session.refresh(sess)
    assert sess.priority_stale is True
    
    get_res = client.get(f"/api/v1/sessions/{sess.id}/priorities")
    assert get_res.json()["stale"] is True

def test_teacher_reorder_protects_regeneration(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g = LearningGroup(session_id=sess.id, name="G", group_type=GroupType.EXTENSION, sort_order=0)
    db_session.add(g)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g.id, student_id=s.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={"ordered_group_ids": [str(g.id)], "reason": "T"})
    
    r1 = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={"replace_existing": True, "force_replace_teacher_priority": False})
    assert r1.status_code == 409
    assert r1.json()["error"]["code"] == "CONFLICT"
    
    r2 = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={"replace_existing": True, "force_replace_teacher_priority": True})
    assert r2.status_code == 200
    assert r2.json()["priorities"][0]["teacher_override_reason"] is None

def test_group_regeneration_clears_priorities(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c, status=SessionStatus.ATTENDANCE_RECORDED)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res_gen1 = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={})
    assert res_gen1.status_code == 200
    
    db_session.refresh(sess)
    assert sess.status == SessionStatus.GROUPED
    
    res_p1 = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    assert res_p1.status_code == 200
    db_session.refresh(sess)
    assert sess.priority_generated_at is not None
    assert db_session.query(GroupPriority).count() > 0
    
    # Regenerate
    res_gen2 = client.post(f"/api/v1/sessions/{sess.id}/groups/generate", json={"replace_existing": True, "force_replace_teacher_edits": True})
    assert res_gen2.status_code == 200
    
    db_session.refresh(sess)
    assert db_session.query(GroupPriority).count() == 0
    assert sess.priority_generated_at is None
    assert sess.priority_stale is False
    assert sess.status == SessionStatus.GROUPED

def test_initial_rollback_after_one_new_row_flushed(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.EXTENSION, sort_order=1)
    db_session.add_all([g1, g2])
    s1, s2 = Student(classroom_id=c.id, name="S1", grade=1), Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([s1, s2])
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s2.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="Ext"))
    db_session.commit()
    
    flush_count = 0
    successful_priority_flushes = 0
    orig_flush = db_session.flush
    def mock_flush(*args, **kwargs):
        nonlocal flush_count, successful_priority_flushes
        flush_count += 1
        if flush_count == 3:
            raise Exception("Mock Fail")
        ret = orig_flush(*args, **kwargs)
        if flush_count == 2:
            successful_priority_flushes += 1
        return ret
        
    with patch.object(db_session, 'flush', side_effect=mock_flush):
        res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
        
    assert res.status_code == 500
    assert successful_priority_flushes == 1
    assert db_session.query(GroupPriority).count() == 0
    db_session.refresh(sess)
    assert sess.priority_generated_at is None
    assert sess.status == SessionStatus.GROUPED

def test_replacement_rollback_restores_old_state(client, db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.EXTENSION, sort_order=1)
    db_session.add_all([g1, g2])
    s1, s2 = Student(classroom_id=c.id, name="S1", grade=1), Student(classroom_id=c.id, name="S2", grade=1)
    db_session.add_all([s1, s2])
    db_session.flush()
    db_session.add(GroupMembership(session_id=sess.id, group_id=g1.id, student_id=s1.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="E1"))
    db_session.add(GroupMembership(session_id=sess.id, group_id=g2.id, student_id=s2.id, original_group_type=GroupType.EXTENSION.value, assignment_reason="E2"))
    db_session.commit()
    
    orig_res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={})
    p_orig = orig_res.json()["priorities"]
    
    client.post(f"/api/v1/sessions/{sess.id}/priorities/reorder", json={
        "ordered_group_ids": [p_orig[1]["group_id"], p_orig[0]["group_id"]],
        "reason": "Old Reason"
    })
    
    db_session.refresh(sess)
    old_gen_at = sess.priority_generated_at
    old_stale = sess.priority_stale
    
    old_rows = (
        db_session.query(GroupPriority)
        .filter(GroupPriority.session_id == sess.id)
        .order_by(GroupPriority.priority_rank)
        .all()
    )
    snapshot = []
    for row in old_rows:
        snapshot.append({
            "id": row.id,
            "group_id": row.group_id,
            "priority_score": row.priority_score,
            "priority_rank": row.priority_rank,
            "priority_tier": row.priority_tier,
            "teacher_rank": row.teacher_rank,
            "teacher_override_reason": row.teacher_override_reason,
            "factor_breakdown": row.factor_breakdown,
            "reasons": row.reasons,
            "top_reason": row.top_reason,
            "student_count_at_generation": row.student_count_at_generation,
        })
    
    flush_count = 0
    successful_priority_flushes = 0
    orig_flush = db_session.flush
    def mock_flush(*args, **kwargs):
        nonlocal flush_count, successful_priority_flushes
        flush_count += 1
        if flush_count == 3:
            raise Exception("Mock Fail")
        ret = orig_flush(*args, **kwargs)
        if flush_count == 2:
            successful_priority_flushes += 1
        return ret
        
    with patch.object(db_session, 'flush', side_effect=mock_flush):
        fail_res = client.post(f"/api/v1/sessions/{sess.id}/priorities/generate", json={
            "replace_existing": True,
            "force_replace_teacher_priority": True
        })
        
    assert fail_res.status_code == 500
    assert successful_priority_flushes == 1
    
    restored_db_rows = (
        db_session.query(GroupPriority)
        .filter(GroupPriority.session_id == sess.id)
        .order_by(GroupPriority.priority_rank)
        .all()
    )
    assert len(restored_db_rows) == 2
    
    for idx, new_row in enumerate(restored_db_rows):
        old_snap = snapshot[idx]
        assert new_row.id == old_snap["id"]
        assert new_row.group_id == old_snap["group_id"]
        assert new_row.priority_score == old_snap["priority_score"]
        assert new_row.priority_rank == old_snap["priority_rank"]
        assert new_row.priority_tier == old_snap["priority_tier"]
        assert new_row.teacher_rank == old_snap["teacher_rank"]
        assert new_row.teacher_override_reason == old_snap["teacher_override_reason"]
        assert new_row.factor_breakdown == old_snap["factor_breakdown"]
        assert new_row.reasons == old_snap["reasons"]
        assert new_row.top_reason == old_snap["top_reason"]
        assert new_row.student_count_at_generation == old_snap["student_count_at_generation"]
        
    db_session.refresh(sess)
    assert sess.priority_generated_at == old_gen_at
    assert sess.priority_stale == old_stale

def test_db_uniqueness_and_bounds(db_session):
    c = setup_base(db_session)
    sess, c_t = setup_session_with_groups(db_session, c)
    g1 = LearningGroup(session_id=sess.id, name="G1", group_type=GroupType.EXTENSION, sort_order=0)
    g2 = LearningGroup(session_id=sess.id, name="G2", group_type=GroupType.EXTENSION, sort_order=1)
    db_session.add_all([g1, g2])
    db_session.commit()
    
    def try_insert(**overrides):
        values = {
            "session_id": sess.id,
            "group_id": g1.id,
            "priority_score": 50,
            "priority_rank": 1,
            "priority_tier": "high",
            "instructional_need_score": 0,
            "evidence_severity_score": 0,
            "uncertainty_score": 0,
            "missed_instruction_score": 0,
            "group_complexity_score": 0,
            "reach_score": 0,
            "factor_breakdown": {},
            "reasons": [],
            "top_reason": "test",
            "student_count_at_generation": 1,
        }
        values.update(overrides)
        if "id" not in values:
            values["id"] = uuid.uuid4()
            
        p = GroupPriority(**values)
        db_session.add(p)
        db_session.commit()
    
    try_insert()
    db_session.query(GroupPriority).delete()
    db_session.commit()
    
    with pytest.raises(IntegrityError):
        try_insert(priority_score=-1)
    db_session.rollback()
    
    with pytest.raises(IntegrityError):
        try_insert(priority_score=101)
    db_session.rollback()
    
    with pytest.raises(IntegrityError):
        try_insert(priority_rank=0)
    db_session.rollback()
    
    with pytest.raises(IntegrityError):
        try_insert(teacher_rank=0)
    db_session.rollback()
    
    with pytest.raises(IntegrityError):
        try_insert(instructional_need_score=-1)
    db_session.rollback()
    
    with pytest.raises(IntegrityError):
        try_insert(evidence_severity_score=-1)
    db_session.rollback()

    with pytest.raises(IntegrityError):
        try_insert(uncertainty_score=-1)
    db_session.rollback()

    with pytest.raises(IntegrityError):
        try_insert(missed_instruction_score=-1)
    db_session.rollback()

    with pytest.raises(IntegrityError):
        try_insert(group_complexity_score=-1)
    db_session.rollback()

    with pytest.raises(IntegrityError):
        try_insert(reach_score=-1)
    db_session.rollback()

    with pytest.raises(IntegrityError):
        try_insert(priority_tier="invalid value")
    db_session.rollback()
    
    with pytest.raises(IntegrityError):
        try_insert(student_count_at_generation=0)
    db_session.rollback()
    
    # 1. Test SAME GROUP, DIFFERENT RANK (Unique group_id per session)
    try_insert(priority_rank=1, group_id=g1.id)
    with pytest.raises(IntegrityError):
        try_insert(priority_rank=2, group_id=g1.id)
    db_session.rollback()
    
    db_session.query(GroupPriority).delete()
    db_session.commit()
    
    # 2. Test DIFFERENT GROUP, SAME RANK (Unique priority_rank per session)
    try_insert(priority_rank=1, group_id=g1.id)
    with pytest.raises(IntegrityError):
        try_insert(priority_rank=1, group_id=g2.id)
    db_session.rollback()



