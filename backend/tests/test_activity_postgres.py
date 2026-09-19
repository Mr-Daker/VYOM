import pytest
pytestmark = pytest.mark.postgres

import pytest
import uuid
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.all_models import (
    User, Classroom, ActivityPlan, GroupActivity, ActivitySourceCitation, 
    ClassSession, LearningGroup, Competency, CurriculumDocument, CurriculumChunk
)
from datetime import date
from sqlalchemy import text
from alembic.config import Config
from alembic import command
import os

@pytest.fixture
def activity_postgres_db(postgres_db_engine, monkeypatch):
    assert postgres_db_engine.url.database and postgres_db_engine.url.database.endswith("_test")
    with postgres_db_engine.connect() as conn:
        res = conn.execute(text("SELECT current_database()"))
        assert res.scalar() == postgres_db_engine.url.database
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.commit()

    from app.core.config import settings
    monkeypatch.setattr(settings, "DATABASE_URL", str(postgres_db_engine.url))
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", str(postgres_db_engine.url))
    
    command.upgrade(alembic_cfg, "008_grounded_activity_generation")
    
    with postgres_db_engine.connect() as conn:
        res = conn.execute(text("SELECT current_database()"))
        assert res.scalar() == postgres_db_engine.url.database
        res = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = res.scalar()
        assert version == "008_grounded_activity_generation"

    yield postgres_db_engine

    

def create_valid_parents(session: Session):
    from app.models.enums import UserRole, SessionStatus
    teacher = User(id=uuid.uuid4(), name="T", email=f"{uuid.uuid4()}@example.com", password_hash="h", role=UserRole.TEACHER)
    session.add(teacher)
    
    classroom = Classroom(id=uuid.uuid4(), name="C", default_duration_minutes=45, max_groups=4, teacher_id=teacher.id)
    session.add(classroom)
    
    comp = Competency(id=uuid.uuid4(), code="C1", name="C1", subject="math", grade=1)
    session.add(comp)
    
    sess = ClassSession(id=uuid.uuid4(), classroom_id=classroom.id, target_competency_id=comp.id, date=date.today(), status=SessionStatus.SCHEDULED, duration_minutes=45)
    session.add(sess)
    
    grp = LearningGroup(id=uuid.uuid4(), session_id=sess.id, group_type="recovery", focus_competency_id=comp.id, name="Rec", reason="reason", sort_order=1)
    session.add(grp)
    
    grp2 = LearningGroup(id=uuid.uuid4(), session_id=sess.id, group_type="check", focus_competency_id=comp.id, name="Chk", reason="reason", sort_order=2)
    session.add(grp2)

    doc = CurriculumDocument(id=uuid.uuid4(), title="Doc", source_type="textbook", source_name="N", subject="math", language="en", version="1", checksum="chk", status="ready", embedding_status="ready")
    session.add(doc)
    
    chunk = CurriculumChunk(id=uuid.uuid4(), document_id=doc.id, chunk_index=0, text="A", text_hash="A")
    session.add(chunk)
    
    session.commit()
    return teacher, classroom, comp, sess, grp, grp2, chunk

def build_valid_plan(sess):
    return ActivityPlan(id=uuid.uuid4(), session_id=sess.id, prompt_version="v1", provider_name="fake", model_name="fake", status="draft", language="en")

def build_valid_activity(plan, sess, comp, grp, generation_order=0):
    return GroupActivity(
        id=uuid.uuid4(), activity_plan_id=plan.id, session_id=sess.id, group_id=grp.id,
        group_name_snapshot=grp.name, group_type_snapshot=grp.group_type, focus_competency_id=comp.id,
        title="T", objective="O", duration_minutes=45, teacher_attention_minutes=15, independent_minutes=30,
        materials=[], teacher_actions=[], student_actions=[], checks_for_understanding=[], success_criteria=[], adaptations=[],
        generated_by="llm", approval_status="pending_teacher_review", prompt_version="v1", provider_name="fake", model_name="fake",
        prompt_input_hash="hash1", structured_output_hash="hash2", generation_order=generation_order
    )

def test_uq_activity_plan_session(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, _, sess, _, _, _ = create_valid_parents(session)
        p1 = build_valid_plan(sess)
        session.add(p1)
        session.commit()
        
        p2 = build_valid_plan(sess)
        session.add(p2)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_activity_plan_status(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, _, sess, _, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        p.status = "invalid_status"
        session.add(p)
        with pytest.raises(IntegrityError):
            session.commit()

def test_uq_grp_act_plan_group(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga1 = build_valid_activity(p, sess, comp, grp, 0)
        session.add(ga1)
        session.commit()
        
        ga2 = build_valid_activity(p, sess, comp, grp, 1)
        session.add(ga2)
        with pytest.raises(IntegrityError):
            session.commit()

def test_uq_grp_act_plan_order(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp1, grp2, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga1 = build_valid_activity(p, sess, comp, grp1, 0)
        session.add(ga1)
        session.commit()
        
        ga2 = build_valid_activity(p, sess, comp, grp2, 0) # duplicate order
        session.add(ga2)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_grp_act_duration(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        ga.duration_minutes = 0
        session.add(ga)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_grp_act_teacher_min(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        ga.teacher_attention_minutes = -1
        session.add(ga)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_grp_act_indep_min(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        ga.independent_minutes = -1
        session.add(ga)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_grp_act_approval(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        ga.approval_status = "approved" # Not allowed in V1 yet
        session.add(ga)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_grp_act_generated_by(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        ga.generated_by = "human" # Not allowed in V1 yet
        session.add(ga)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_grp_act_generation_order(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, _ = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, -1)
        session.add(ga)
        with pytest.raises(IntegrityError):
            session.commit()

def test_uq_act_cit_activity_chunk(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, chunk = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        session.add(ga)
        session.commit()
        
        cit1 = ActivitySourceCitation(
            id=uuid.uuid4(), group_activity_id=ga.id, curriculum_chunk_id=chunk.id, citation_order=0,
            document_id_snapshot=chunk.document_id, document_title_snapshot="Doc", source_name_snapshot="N",
            source_type_snapshot="textbook", version_snapshot="1", chunk_index_snapshot=0
        )
        session.add(cit1)
        session.commit()
        
        cit2 = ActivitySourceCitation(
            id=uuid.uuid4(), group_activity_id=ga.id, curriculum_chunk_id=chunk.id, citation_order=1,
            document_id_snapshot=chunk.document_id, document_title_snapshot="Doc", source_name_snapshot="N",
            source_type_snapshot="textbook", version_snapshot="1", chunk_index_snapshot=0
        )
        session.add(cit2)
        with pytest.raises(IntegrityError):
            session.commit()

def test_chk_act_cit_order(activity_postgres_db):
    with Session(activity_postgres_db) as session:
        _, _, comp, sess, grp, _, chunk = create_valid_parents(session)
        p = build_valid_plan(sess)
        session.add(p)
        session.commit()
        
        ga = build_valid_activity(p, sess, comp, grp, 0)
        session.add(ga)
        session.commit()
        
        cit = ActivitySourceCitation(
            id=uuid.uuid4(), group_activity_id=ga.id, curriculum_chunk_id=chunk.id, citation_order=-1,
            document_id_snapshot=chunk.document_id, document_title_snapshot="Doc", source_name_snapshot="N",
            source_type_snapshot="textbook", version_snapshot="1", chunk_index_snapshot=0
        )
        session.add(cit)
        with pytest.raises(IntegrityError):
            session.commit()

def test_pg_migration_names_match_008(activity_postgres_db):
    with activity_postgres_db.connect() as conn:
        res = conn.execute(text("SELECT conname FROM pg_constraint"))
        constraints = [row[0] for row in res]
        expected = [
            'uq_activity_plan_session', 'chk_activity_plan_status',
            'chk_grp_act_approval', 'chk_grp_act_duration', 'chk_grp_act_generated_by', 
            'chk_grp_act_indep_min', 'chk_grp_act_teacher_min', 'chk_grp_act_generation_order',
            'uq_grp_act_plan_group', 'uq_grp_act_plan_order',
            'chk_act_cit_order', 'uq_act_cit_activity_chunk'
        ]
        for c in expected:
            assert c in constraints

