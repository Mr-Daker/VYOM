import pytest
import os
import uuid
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models.all_models import (
    Classroom, ClassSession, Competency, RotationPlan, RotationSlot, utc_now, User, LearningGroup
)
from app.models.enums import SessionStatus, UserRole

@pytest.fixture(scope="function")
def alembic_postgres_db(postgres_db_engine):
    import alembic.config
    import alembic.command
    from app.core.config import settings

    url = str(postgres_db_engine.url)
    
    with postgres_db_engine.begin() as conn:
        res = conn.execute(text("SELECT current_database()")).scalar()
        assert res.endswith("_test"), f"Database {res} is not a test database!"
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        
    old_url = settings.DATABASE_URL
    try:
        settings.DATABASE_URL = url
        alembic_cfg = alembic.config.Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", url)
        alembic.command.upgrade(alembic_cfg, "head")
    finally:
        settings.DATABASE_URL = old_url
        
    return postgres_db_engine

@pytest.fixture
def pg_session(alembic_postgres_db):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=alembic_postgres_db)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

def setup_base(db):
    teacher = User(
        name="Postgres Teacher",
        email=f"pgteacher-{uuid.uuid4()}@example.com",
        password_hash="test",
        role=UserRole.TEACHER.value,
    )
    db.add(teacher)
    db.flush()

    c = Classroom(name="PG Room", default_duration_minutes=45, max_groups=4, teacher_id=teacher.id)
    db.add(c)
    db.flush()
    
    t = Competency(name="Tgt", code=f"TGT-{uuid.uuid4()}", subject="math", grade=1)
    db.add(t)
    db.flush()
    
    s = ClassSession(
        classroom_id=c.id,
        target_competency_id=t.id,
        status='grouped',
        duration_minutes=45,
    )
    db.add(s)
    db.commit()
    return s

def test_rotation_plan_constraints(pg_session):
    s = setup_base(pg_session)
    
    def valid_plan():
        return RotationPlan(
            session_id=s.id, session_duration_minutes=45, opening_minutes=3, closing_minutes=2,
            transition_minutes_each=1, transition_total_minutes=2, teacher_attention_budget_minutes=38,
            minimum_group_attention_minutes=3, group_count=3, algorithm_version="v1"
        )
        
    plan = valid_plan()
    pg_session.add(plan)
    pg_session.commit()
    
    # duplicate session
    p2 = valid_plan()
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "uq_rotation_plan_session_id" in str(exc.value)
    pg_session.rollback()
    
    # session_duration <= 0
    p2 = valid_plan()
    p2.session_duration_minutes = 0
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_session_duration" in str(exc.value)
    pg_session.rollback()
    
    # opening < 0
    p2 = valid_plan()
    p2.opening_minutes = -1
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_opening_minutes" in str(exc.value)
    pg_session.rollback()
    
    # closing < 0
    p2 = valid_plan()
    p2.closing_minutes = -1
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_closing_minutes" in str(exc.value)
    pg_session.rollback()

    # transition_minutes_each < 0
    p2 = valid_plan()
    p2.transition_minutes_each = -1
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_trans_min_each" in str(exc.value)
    pg_session.rollback()

    # transition_total < 0
    p2 = valid_plan()
    p2.transition_total_minutes = -1
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_trans_total" in str(exc.value)
    pg_session.rollback()
    
    # teacher_attention_budget <= 0
    p2 = valid_plan()
    p2.teacher_attention_budget_minutes = 0
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_budget" in str(exc.value)
    pg_session.rollback()
    
    # minimum_group_attention <= 0
    p2 = valid_plan()
    p2.minimum_group_attention_minutes = 0
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_min_group_attention" in str(exc.value)
    pg_session.rollback()
    
    # group_count <= 0
    p2 = valid_plan()
    p2.group_count = 0
    p2.session_id = setup_base(pg_session).id
    pg_session.add(p2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rp_group_count" in str(exc.value)
    pg_session.rollback()

def test_rotation_slot_constraints(pg_session):
    s = setup_base(pg_session)
    plan = RotationPlan(session_id=s.id, session_duration_minutes=45, opening_minutes=3, closing_minutes=2, transition_minutes_each=1, transition_total_minutes=2, teacher_attention_budget_minutes=38, minimum_group_attention_minutes=3, group_count=3, algorithm_version="v1")
    pg_session.add(plan)
    
    g = LearningGroup(session_id=s.id, name="G", group_type="check", sort_order=0, reason="")
    pg_session.add(g)
    pg_session.commit()
    
    def valid_slot(seq=0):
        return RotationSlot(
            rotation_plan_id=plan.id, session_id=s.id, sequence_index=seq, slot_type='group_visit',
            group_id=g.id, start_minute=3, end_minute=10, duration_minutes=7,
            group_name_snapshot="G", group_type_snapshot="check", priority_score_snapshot=50.0,
            algorithm_priority_rank_snapshot=1, effective_rank_snapshot=1,
            student_count_snapshot=1, base_minutes=3, weighted_extra_minutes=4, reason="test"
        )
        
    s1 = valid_slot(0)
    pg_session.add(s1)
    pg_session.commit()
    
    # duplicate sequence
    s2 = valid_slot(0)
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "uq_rotation_slot_seq" in str(exc.value)
    pg_session.rollback()
    
    # sequence < 0
    s2 = valid_slot(1)
    s2.sequence_index = -1
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rs_seq_index" in str(exc.value)
    pg_session.rollback()
    
    # start < 0
    s2 = valid_slot(1)
    s2.start_minute = -1
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rs_start_minute" in str(exc.value)
    pg_session.rollback()
    
    # end <= start
    s2 = valid_slot(1)
    s2.end_minute = 3
    s2.duration_minutes = 0
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rs_end_gt_start" in str(exc.value)
    pg_session.rollback()
    
    # duration <= 0
    s2 = valid_slot(1)
    s2.duration_minutes = 0
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rs_duration_gt_zero" in str(exc.value)
    pg_session.rollback()
    
    # duration != end-start
    s2 = valid_slot(1)
    s2.duration_minutes = 99
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rs_duration_calc" in str(exc.value)
    pg_session.rollback()    # group_visit group_id NULL
    s2 = valid_slot(1)
    s2.group_id = None
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    pg_session.rollback()
    
    # non-group slot group_id NOT NULL
    s2 = valid_slot(1)
    s2.slot_type = 'transition'
    # group_id is already set
    pg_session.add(s2)
    with pytest.raises(IntegrityError) as exc:
        pg_session.flush()
    assert "chk_rs_group_id_semantics" in str(exc.value)
    pg_session.rollback()

    
    seq_counter = [1]
    def next_sequence():
        seq_counter[0] += 1
        return seq_counter[0]

    def assert_snapshot_constraint_failure(**overrides):
        slot = valid_slot(next_sequence())

        for field, value in overrides.items():
            setattr(slot, field, value)

        pg_session.add(slot)

        with pytest.raises(IntegrityError) as exc:
            pg_session.flush()

        assert (
            "chk_rs_group_visit_snapshot"
            in str(exc.value)
        )

        pg_session.rollback()

    assert_snapshot_constraint_failure(group_name_snapshot = None)
    assert_snapshot_constraint_failure(group_type_snapshot = None)
    assert_snapshot_constraint_failure(priority_score_snapshot = None)
    assert_snapshot_constraint_failure(algorithm_priority_rank_snapshot = None)
    assert_snapshot_constraint_failure(effective_rank_snapshot = None)
    assert_snapshot_constraint_failure(student_count_snapshot = None)
    assert_snapshot_constraint_failure(base_minutes = None)
    assert_snapshot_constraint_failure(weighted_extra_minutes = None)
    assert_snapshot_constraint_failure(reason = None)
    
    assert_snapshot_constraint_failure(priority_score_snapshot=-1)
    assert_snapshot_constraint_failure(priority_score_snapshot=101)
    assert_snapshot_constraint_failure(algorithm_priority_rank_snapshot=0)
    assert_snapshot_constraint_failure(effective_rank_snapshot=0)
    assert_snapshot_constraint_failure(student_count_snapshot=0)
    assert_snapshot_constraint_failure(base_minutes=0)
    assert_snapshot_constraint_failure(weighted_extra_minutes=-1)

def test_pg_migration_names_match(alembic_postgres_db):
    with alembic_postgres_db.connect() as conn:
        res = conn.execute(text("SELECT conname FROM pg_constraint WHERE conname LIKE 'chk_rp_%' OR conname LIKE 'chk_rs_%' OR conname LIKE 'uq_rotation%'")).fetchall()
        names = [r[0] for r in res]
        assert "chk_rp_session_duration" in names
        assert "chk_rp_opening_minutes" in names
        assert "chk_rp_closing_minutes" in names
        assert "chk_rp_trans_min_each" in names
        assert "chk_rp_trans_total" in names
        assert "chk_rp_budget" in names
        assert "chk_rp_min_group_attention" in names
        assert "chk_rp_group_count" in names
        
        assert "chk_rs_seq_index" in names
        assert "chk_rs_start_minute" in names
        assert "chk_rs_end_gt_start" in names
        assert "chk_rs_duration_gt_zero" in names
        assert "chk_rs_duration_calc" in names
        assert "chk_rs_group_id_semantics" in names
        assert "chk_rs_group_visit_snapshot" in names
        
        assert "uq_rotation_plan_session_id" in names
        assert "uq_rotation_slot_seq" in names
