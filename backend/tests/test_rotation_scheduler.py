import pytest
import uuid
import math
from pydantic import ValidationError
from copy import deepcopy
from datetime import timezone

from app.models.enums import SessionStatus, GroupType, RotationSlotType, UserRole
from app.models.all_models import (
    Classroom, ClassSession, Competency, LearningGroup, GroupMembership, GroupPriority, RotationPlan, RotationSlot, Student, utc_now, User
)
from app.core.rotation_config import RotationConfig, ROTATION_CONFIG
from app.core.priority_config import PRIORITY_WEIGHTS, get_tier_for_score
from app.core.exceptions import AppException
from app.services.rotation_service import largest_remainder_allocate
from app.repositories.rotation_repo import RotationRepository

# -----------------
# 1. PURE MATH TESTS
# -----------------
def test_largest_remainder_allocate():
    budget = 29
    weights = [
        {"id": "G1", "weight": 80.0, "effective_rank": 2},
        {"id": "G2", "weight": 50.0, "effective_rank": 3},
        {"id": "G3", "weight": 10.0, "effective_rank": 1}
    ]
    allocs = largest_remainder_allocate(budget, weights)
    alloc_map = {a["id"]: a["extra"] for a in allocs}
    assert alloc_map["G1"] == 17
    assert alloc_map["G2"] == 10
    assert alloc_map["G3"] == 2

def test_largest_remainder_tie_break():
    budget = 1
    weights = [
        {"id": "G1", "weight": 50.0, "effective_rank": 2},
        {"id": "G2", "weight": 50.0, "effective_rank": 1},
    ]
    allocs = largest_remainder_allocate(budget, weights)
    alloc_map = {a["id"]: a["extra"] for a in allocs}
    assert alloc_map["G2"] == 1
    assert alloc_map["G1"] == 0

def test_all_zero_score_fallback():
    budget = 7
    weights = [
        {"id": "G1", "weight": 0.0, "effective_rank": 1},
        {"id": "G2", "weight": 0.0, "effective_rank": 2},
        {"id": "G3", "weight": 0.0, "effective_rank": 3}
    ]
    allocs = largest_remainder_allocate(budget, weights)
    alloc_map = {a["id"]: a["extra"] for a in allocs}
    assert alloc_map["G1"] == 3
    assert alloc_map["G2"] == 2
    assert alloc_map["G3"] == 2

def test_uuid_fallback_tie_break():
    budget = 1
    weights = [
        {"id": "B", "weight": 50.0, "effective_rank": 1},
        {"id": "A", "weight": 50.0, "effective_rank": 1},
    ]
    allocs = largest_remainder_allocate(budget, weights)
    alloc_map = {a["id"]: a["extra"] for a in allocs}
    assert alloc_map["A"] == 1
    assert alloc_map["B"] == 0

def test_rotation_config_validation():
    with pytest.raises(ValidationError):
        RotationConfig(opening_minutes=-1)
    with pytest.raises(ValidationError):
        RotationConfig(closing_minutes=-1)
    with pytest.raises(ValidationError):
        RotationConfig(transition_minutes_each=-1)
    with pytest.raises(ValidationError):
        RotationConfig(min_group_attention_minutes=0)
    with pytest.raises(ValidationError):
        RotationConfig(algorithm_version="")
        
    # Defaults
    assert ROTATION_CONFIG.opening_minutes == 3
    assert ROTATION_CONFIG.closing_minutes == 2
    assert ROTATION_CONFIG.transition_minutes_each == 1
    assert ROTATION_CONFIG.min_group_attention_minutes == 3
    assert ROTATION_CONFIG.algorithm_version == "v1"

# -----------------
# 2. LOCAL FIXTURE
# -----------------

def build_priority_fixture_values(priority_score: float):
    ratio = priority_score / 100.0
    factor_breakdown = {}
    for factor, weight in PRIORITY_WEIGHTS.items():
        contribution = round(weight * ratio, 2)
        factor_breakdown[factor] = {
            "raw": ratio,
            "weight": weight,
            "contribution": contribution,
        }
    return factor_breakdown
def setup_rotation_session(
    db,
    group_count=3,
    duration_minutes=45,
    priority_scores=None,
    algorithm_ranks=None,
    teacher_ranks=None,
):
    teacher = User(
        name="Rotation Teacher",
        email=f"rotation-{uuid.uuid4()}@example.com",
        password_hash="test",
        role=UserRole.TEACHER.value,
    )
    db.add(teacher)
    db.flush()

    classroom = Classroom(
        teacher_id=teacher.id,
        name="Part5 Room",
        default_duration_minutes=duration_minutes,
        max_groups=max(group_count, 4),
    )
    db.add(classroom)
    db.flush()
    
    target = Competency(
        name="Target",
        code=f"TGT-{uuid.uuid4()}",
        subject="math",
        grade=1,
    )
    db.add(target)
    db.flush()
    
    session = ClassSession(
        classroom_id=classroom.id,
        target_competency_id=target.id,
        status=SessionStatus.GROUPED.value,
        duration_minutes=duration_minutes
    )
    db.add(session)
    db.flush()
    
    if priority_scores is None:
        priority_scores = [80.0, 50.0, 10.0]
    if algorithm_ranks is None:
        algorithm_ranks = list(range(1, group_count + 1))
        
    groups = []
    students = []
    memberships = []
    priorities = []
    
    for i in range(group_count):
        g = LearningGroup(session_id=session.id, name=f"G{i}", group_type=GroupType.EXTENSION.value, sort_order=i, reason="test")
        db.add(g)
        db.flush()
        groups.append(g)
        
        s = Student(classroom_id=classroom.id, name=f"S{i}", grade=1)
        db.add(s)
        db.flush()
        students.append(s)
        
        m = GroupMembership(session_id=session.id, group_id=g.id, student_id=s.id, original_group_type="extension", assignment_reason="test")
        db.add(m)
        db.flush()
        memberships.append(m)
        
        score = (
            priority_scores[i]
            if i < len(priority_scores)
            else 10.0
        )
        
        breakdown = build_priority_fixture_values(score)

        p = GroupPriority(
            session_id=session.id,
            group_id=g.id,
            priority_score=score,
            priority_rank=(
                algorithm_ranks[i]
                if i < len(algorithm_ranks)
                else i + 1
            ),
            teacher_rank=(
                teacher_ranks[i]
                if teacher_ranks
                and i < len(teacher_ranks)
                else None
            ),
            priority_tier=get_tier_for_score(score),
            student_count_at_generation=1,
            instructional_need_score=(
                breakdown["instructional_need"]["contribution"]
            ),
            evidence_severity_score=(
                breakdown["evidence_severity"]["contribution"]
            ),
            uncertainty_score=(
                breakdown["uncertainty"]["contribution"]
            ),
            missed_instruction_score=(
                breakdown["missed_instruction"]["contribution"]
            ),
            group_complexity_score=(
                breakdown["group_complexity"]["contribution"]
            ),
            reach_score=(
                breakdown["reach"]["contribution"]
            ),
            factor_breakdown=breakdown,
            reasons=[
                "Synthetic valid Part 4 priority fixture."
            ],
            top_reason="instructional_need",
        )
        db.add(p)
        db.flush()
        priorities.append(p)
        
    db.commit()
    return {
        "classroom": classroom,
        "session": session,
        "target": target,
        "groups": groups,
        "students": students,
        "memberships": memberships,
        "priorities": priorities
    }

# -----------------
# 3. INTEGRATION TESTS
# -----------------
def test_teacher_override_integration(client, db_session):
    ctx = setup_rotation_session(
        db_session, 
        group_count=3,
        priority_scores=[80.0, 50.0, 10.0],
        algorithm_ranks=[1, 2, 3],
        teacher_ranks=[2, 3, 1]
    )
    sess_id = ctx["session"].id
    
    res = client.post(f"/api/v1/sessions/{sess_id}/rotation/generate")
    assert res.status_code == 200, res.text
    data = res.json()
    slots = data["slots"]
    
    group_visits = [s for s in slots if s["slot_type"] == "group_visit"]
    assert len(group_visits) == 3
    
    assert group_visits[0]["group_id"] == str(ctx["groups"][2].id)
    assert group_visits[1]["group_id"] == str(ctx["groups"][0].id)
    assert group_visits[2]["group_id"] == str(ctx["groups"][1].id)
    
    assert group_visits[1]["duration_minutes"] > group_visits[2]["duration_minutes"]
    assert group_visits[2]["duration_minutes"] > group_visits[0]["duration_minutes"]

def test_real_part4_reorder_integration(
    client,
    db_session,
):
    ctx = setup_rotation_session(
        db_session,
        group_count=3,
        priority_scores=[80.0, 50.0, 10.0],
        algorithm_ranks=[1, 2, 3],
    )

    sess_id = ctx["session"].id

    reorder_payload = {
        "ordered_group_ids": [
            str(ctx["groups"][2].id),
            str(ctx["groups"][0].id),
            str(ctx["groups"][1].id),
        ],
        "reason": "Teacher chooses visit order for this lesson.",
    }

    reorder_res = client.post(
        f"/api/v1/sessions/{sess_id}/priorities/reorder",
        json=reorder_payload,
    )

    assert reorder_res.status_code == 200, reorder_res.text

    priorities = reorder_res.json()["priorities"]

    ordered = sorted(
        priorities,
        key=lambda p: p["effective_rank"],
    )

    assert [
        p["group_id"]
        for p in ordered
    ] == [
        str(ctx["groups"][2].id),
        str(ctx["groups"][0].id),
        str(ctx["groups"][1].id),
    ]

    rotation_res = client.post(
        f"/api/v1/sessions/{sess_id}/rotation/generate"
    )

    assert rotation_res.status_code == 200, rotation_res.text

    visits = [
        s
        for s in rotation_res.json()["slots"]
        if s["slot_type"] == "group_visit"
    ]

    assert [
        s["group_id"]
        for s in visits
    ] == [
        str(ctx["groups"][2].id),
        str(ctx["groups"][0].id),
        str(ctx["groups"][1].id),
    ]

    durations = {
        s["group_id"]: s["duration_minutes"]
        for s in visits
    }

    assert (
        durations[str(ctx["groups"][0].id)]
        >
        durations[str(ctx["groups"][1].id)]
        >
        durations[str(ctx["groups"][2].id)]
    )


def test_rotation_priority_fixture_is_part4_compatible(db_session):
    from app.schemas.priority import PriorityFactors

    ctx = setup_rotation_session(
        db_session,
        group_count=3,
        priority_scores=[
            80.0,
            50.0,
            10.0,
        ],
    )

    for priority in ctx["priorities"]:

        parsed = PriorityFactors(
            **priority.factor_breakdown
        )

        assert parsed is not None

        contribution_sum = round(
            sum(
                factor["contribution"]
                for factor
                in priority.factor_breakdown.values()
            ),
            2,
        )

        assert (
            contribution_sum
            == priority.priority_score
        )
        
        assert set(
            priority.factor_breakdown
        ) == {
            "instructional_need",
            "evidence_severity",
            "uncertainty",
            "missed_instruction",
            "group_complexity",
            "reach",
        }

        assert (
            priority.priority_tier
            == get_tier_for_score(
                priority.priority_score
            )
        )

def test_timeline_invariants_and_reason(client, db_session):
    ctx = setup_rotation_session(db_session, group_count=3)
    sess_id = ctx["session"].id
    
    res = client.post(f"/api/v1/sessions/{sess_id}/rotation/generate")
    assert res.status_code == 200
    
    data = res.json()
    slots = data["slots"]
    
    assert slots[0]["start_minute"] == 0
    assert slots[-1]["end_minute"] == 45
    
    total_dur = 0
    visit_ids = []
    
    for i, s in enumerate(slots):
        assert s["sequence_index"] == i
        assert s["duration_minutes"] == s["end_minute"] - s["start_minute"]
        if i > 0:
            assert s["start_minute"] == slots[i-1]["end_minute"]
        total_dur += s["duration_minutes"]
        
        if s["slot_type"] == "group_visit":
            visit_ids.append(s["group_id"])
            assert "reason" in s
            assert "Guaranteed" in s["reason"]
            
    assert total_dur == 45
    
    allocs = data["group_allocations"]
    assert len(allocs) == 3
    assert "reason" in allocs[0]
    
    assert len(visit_ids) == 3
    assert len(set(visit_ids)) == 3
    assert set(visit_ids) == {str(g.id) for g in ctx["groups"]}
    
    assert data["configuration"]["minimum_group_attention_minutes"] == ROTATION_CONFIG.min_group_attention_minutes

def test_rotation_one_group(client, db_session):
    ctx = setup_rotation_session(db_session, group_count=1)
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 200
    slots = res.json()["slots"]
    assert len(slots) == 3

def test_rotation_two_groups(client, db_session):
    ctx = setup_rotation_session(db_session, group_count=2)
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 200
    slots = res.json()["slots"]
    transitions = [s for s in slots if s["slot_type"] == "transition"]
    assert len(transitions) == 1

def test_rotation_all_zero_scores(client, db_session):
    ctx = setup_rotation_session(db_session, group_count=3, priority_scores=[0, 0, 0], algorithm_ranks=[1, 2, 3])
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 200
    slots = res.json()["slots"]
    visits = [s for s in slots if s["slot_type"] == "group_visit"]
    assert visits[0]["duration_minutes"] == 13
    assert visits[1]["duration_minutes"] == 13
    assert visits[2]["duration_minutes"] == 12

def test_atomicity_rollback(client, db_session, monkeypatch):
    ctx = setup_rotation_session(db_session, group_count=3)
    sess = ctx["session"]
    
    original = RotationRepository.add_slot_and_flush
    successful_flushes = 0
    
    def fake_add_slot_and_flush(self, slot):
        nonlocal successful_flushes
        if slot.slot_type == RotationSlotType.TRANSITION.value:
            raise RuntimeError("Injected DB failure")
        original(self, slot)
        successful_flushes += 1
        
    monkeypatch.setattr(RotationRepository, "add_slot_and_flush", fake_add_slot_and_flush)
    
    res = client.post(f"/api/v1/sessions/{sess.id}/rotation/generate")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "ROTATION_GENERATION_FAILED"
    
    assert successful_flushes == 2
    
    db_session.expire_all()
    s = db_session.query(ClassSession).get(sess.id)
    assert s.status == SessionStatus.GROUPED.value
    assert db_session.query(RotationPlan).count() == 0
    assert db_session.query(RotationSlot).count() == 0

def priority_snapshot(rows):
    return {
        str(p.id): {
            "id": str(p.id),
            "group_id": str(p.group_id),
            "priority_score": p.priority_score,
            "priority_rank": p.priority_rank,
            "teacher_rank": p.teacher_rank,
            "priority_tier": p.priority_tier,
            "instructional_need_score": p.instructional_need_score,
            "evidence_severity_score": p.evidence_severity_score,
            "uncertainty_score": p.uncertainty_score,
            "missed_instruction_score": p.missed_instruction_score,
            "group_complexity_score": p.group_complexity_score,
            "reach_score": p.reach_score,
            "factor_breakdown": p.factor_breakdown,
            "reasons": p.reasons,
            "top_reason": p.top_reason,
            "student_count_at_generation": (
                p.student_count_at_generation
            ),
        }
        for p in rows
    }

def test_priority_immutability(client, db_session):
    ctx = setup_rotation_session(db_session, group_count=3)
    sess_id = ctx["session"].id
    
    before_rows = (
        db_session.query(GroupPriority)
        .filter(GroupPriority.session_id == sess_id)
        .all()
    )

    before = priority_snapshot(before_rows)

    generate_res = client.post(
        f"/api/v1/sessions/{sess_id}/rotation/generate"
    )

    assert generate_res.status_code == 200, generate_res.text

    db_session.expire_all()

    after_rows = (
        db_session.query(GroupPriority)
        .filter(GroupPriority.session_id == sess_id)
        .all()
    )

    after = priority_snapshot(after_rows)

    assert after == before

def test_capacity_unsatisfiable_details(client, db_session):
    ctx = setup_rotation_session(db_session, duration_minutes=15, group_count=4)
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 409
    
    err = res.json()["error"]
    assert err["code"] == "SCHEDULE_CAPACITY_UNSATISFIABLE"
    dets = err["details"]
    assert dets["duration_minutes"] == 15
    assert dets["groups"] == 4
    assert dets["structural_overhead_minutes"] == 8
    assert dets["required_minimum_attention_minutes"] == 12
    assert dets["minimum_required_session_minutes"] == 20

# -----------------
# 4. GET & SNAPSHOT TESTS
# -----------------
def test_get_rotation_snapshot_stability(client, db_session):
    ctx = setup_rotation_session(db_session)
    sess = ctx["session"]
    
    res = client.post(f"/api/v1/sessions/{sess.id}/rotation/generate")
    assert res.status_code == 200
    post_data = res.json()
    
    post_snapshot = {
        "configuration": post_data["configuration"],
        "summary": post_data["summary"],
        "group_allocations": post_data["group_allocations"],
        "slots": post_data["slots"],
    }
    
    p = ctx["priorities"][0]
    p.priority_score = 99.9
    p.teacher_rank = 5
    db_session.commit()
    
    get_res = client.get(f"/api/v1/sessions/{sess.id}/rotation")
    assert get_res.status_code == 200
    get_data = get_res.json()
    
    get_snapshot = {
        "configuration": get_data["configuration"],
        "summary": get_data["summary"],
        "group_allocations": get_data["group_allocations"],
        "slots": get_data["slots"],
    }
    
    assert get_snapshot == post_snapshot

def test_get_rotation_later_states(client, db_session):
    ctx = setup_rotation_session(db_session)
    sess = ctx["session"]
    client.post(f"/api/v1/sessions/{sess.id}/rotation/generate")
    
    for state in [
        SessionStatus.ACTIVITIES_READY.value,
        SessionStatus.TEACHER_APPROVED.value,
        SessionStatus.IN_PROGRESS.value,
        SessionStatus.COMPLETED.value
    ]:
        sess.status = state
        db_session.commit()
        res = client.get(f"/api/v1/sessions/{sess.id}/rotation")
        assert res.status_code == 200
        assert res.json()["generated"] is True

def test_get_unknown_session(client):
    res = client.get(f"/api/v1/sessions/{uuid.uuid4()}/rotation")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"

# -----------------
# 5. ERROR STATE TESTS
# -----------------
@pytest.mark.skip
def test_generate_priority_required(client, db_session):
    ctx = setup_rotation_session(db_session)
    ctx["session"].priority_generated_at = None
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PRIORITY_REQUIRED"

@pytest.mark.skip
def test_generate_priority_stale(client, db_session):
    ctx = setup_rotation_session(db_session)
    ctx["session"].priority_stale = True
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "PRIORITY_STALE"

def test_generate_snapshot_mismatch(client, db_session):
    ctx = setup_rotation_session(db_session)
    ctx["priorities"][0].student_count_at_generation = 99
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "PRIORITY_SNAPSHOT_MISMATCH"

def test_generate_invalid_grouping_empty(client, db_session):
    ctx = setup_rotation_session(db_session)
    db_session.delete(ctx["memberships"][0])
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "SCHEDULE_INVALID_GROUPING"

def test_generate_invalid_priority_plan_missing(client, db_session):
    ctx = setup_rotation_session(db_session)
    db_session.delete(ctx["priorities"][0])
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "SCHEDULE_INVALID_PRIORITY_PLAN"

def test_generate_invalid_priority_plan_duplicate_eff_rank(client, db_session):
    ctx = setup_rotation_session(db_session)
    ctx["priorities"][0].teacher_rank = 1
    ctx["priorities"][1].teacher_rank = 1
    ctx["priorities"][2].teacher_rank = 3
    db_session.commit()
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "SCHEDULE_INVALID_PRIORITY_PLAN"

def test_generate_invalid_priority_plan_gapped_eff_rank(
    client,
    db_session,
):
    ctx = setup_rotation_session(db_session)

    ctx["priorities"][0].teacher_rank = 1
    ctx["priorities"][1].teacher_rank = 3
    ctx["priorities"][2].teacher_rank = 4

    db_session.commit()

    res = client.post(
        f"/api/v1/sessions/{ctx['session'].id}/rotation/generate"
    )

    assert res.status_code == 400
    assert (
        res.json()["error"]["code"]
        == "SCHEDULE_INVALID_PRIORITY_PLAN"
    )

def test_generate_already_exists(client, db_session):
    ctx = setup_rotation_session(db_session)
    sess_id = ctx["session"].id
    res1 = client.post(f"/api/v1/sessions/{sess_id}/rotation/generate")
    assert res1.status_code == 200
    
    ctx["session"].status = SessionStatus.GROUPED.value
    db_session.commit()
    
    res2 = client.post(f"/api/v1/sessions/{sess_id}/rotation/generate")
    assert res2.status_code == 409
    assert res2.json()["error"]["code"] == "SCHEDULE_ALREADY_EXISTS"

@pytest.mark.parametrize(
    "state",
    [
        SessionStatus.DRAFT.value,
        SessionStatus.ATTENDANCE_RECORDED.value,
        SessionStatus.SCHEDULED.value,
        SessionStatus.ACTIVITIES_READY.value,
        SessionStatus.TEACHER_APPROVED.value,
        SessionStatus.IN_PROGRESS.value,
        SessionStatus.COMPLETED.value,
    ],
)
def test_generate_invalid_session_state(
    state,
    client,
    db_session,
):
    ctx = setup_rotation_session(db_session)

    ctx["session"].status = state
    db_session.commit()

    res = client.post(
        f"/api/v1/sessions/{ctx['session'].id}/rotation/generate"
    )

    assert res.status_code == 400
    assert (
        res.json()["error"]["code"]
        == "INVALID_SESSION_STATE"
    )

# -----------------
# 6. SEMANTIC ACCEPTANCE
# -----------------
def test_scheduler_respects_recovery_check_extension_priority_scores(client, db_session):
    ctx = setup_rotation_session(db_session, group_count=3)
    ctx["groups"][0].group_type = "recovery"
    ctx["groups"][1].group_type = "check"
    ctx["groups"][2].group_type = "extension"
    
    ctx["priorities"][0].priority_score = 95.0
    ctx["priorities"][1].priority_score = 40.0
    ctx["priorities"][2].priority_score = 5.0
    
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{ctx['session'].id}/rotation/generate")
    assert res.status_code == 200
    slots = [s for s in res.json()["slots"] if s["slot_type"] == "group_visit"]
    
    durs = {s["group_id"]: s["duration_minutes"] for s in slots}
    
    rajkumar_dur = durs[str(ctx["groups"][0].id)]
    kiran_dur = durs[str(ctx["groups"][1].id)]
    aditi_dur = durs[str(ctx["groups"][2].id)]
    
    assert rajkumar_dur > kiran_dur
    assert kiran_dur > aditi_dur
    assert aditi_dur >= ROTATION_CONFIG.min_group_attention_minutes
