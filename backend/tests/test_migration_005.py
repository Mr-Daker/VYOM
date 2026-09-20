import pytest
pytestmark = pytest.mark.postgres
import uuid
from sqlalchemy import text
from app.core.config import settings

@pytest.mark.migration
def test_alembic_004_to_005(postgres_db_engine, monkeypatch):
    from alembic.config import Config
    from alembic import command
    
    # 1. Bind Alembic to the exact same postgres test database
    monkeypatch.setattr(settings, "DATABASE_URL", postgres_db_engine.url.render_as_string(hide_password=False))
    
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_db_engine.url.render_as_string(hide_password=False))
    
    # 2. Upgrade to Revision 004
    command.upgrade(alembic_cfg, "004_teacher_priority")
    
    # 3. Connect via Raw SQL to the isolated database
    with postgres_db_engine.begin() as conn:
        # A. Assert actual DB identity
        db_name = conn.execute(text("SELECT current_database();")).scalar()
        assert db_name == postgres_db_engine.url.database
        
        # B. Assert actual Alembic revision
        version_num = conn.execute(text("SELECT version_num FROM alembic_version;")).scalar()
        assert version_num == "004_teacher_priority"
        
        # C. Check column absence (pre-005)
        col_exists = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'group_priorities'
              AND column_name = 'student_count_at_generation';
        """)).scalar()
        assert col_exists is None
        
        # 4. Insert 004 Schema Raw Data
        teacher_id = str(uuid.uuid4())
        conn.execute(
            text("""
                INSERT INTO users (id, email, password_hash, role, name, created_at, updated_at) 
                VALUES (:id, :email, :pwd, 'teacher', :name, now(), now())
            """), 
            {"id": teacher_id, "email": "t@ex.com", "pwd": "pwd", "name": "T"}
        )
        
        class_id = str(uuid.uuid4())
        conn.execute(
            text("""
                INSERT INTO classrooms (id, teacher_id, name, max_groups, created_at, updated_at) 
                VALUES (:id, :t_id, 'Class', 4, now(), now())
            """), 
            {"id": class_id, "t_id": teacher_id}
        )
        
        comp_id = str(uuid.uuid4())
        conn.execute(
            text("""
                INSERT INTO competencies (id, code, subject, name) 
                VALUES (:id, 'T', 'math', 'Target')
            """), 
            {"id": comp_id}
        )
        
        # Create Sessions (Valid/Non-Stale, Stale, Empty Group)
        sess_a, sess_b, sess_c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        for s_id, stale in [(sess_a, False), (sess_b, True), (sess_c, False)]:
            conn.execute(
                text("""
                    INSERT INTO class_sessions (id, classroom_id, target_competency_id, status, date, duration_minutes, priority_stale, priority_generated_at, created_at, updated_at) 
                    VALUES (:id, :c_id, :comp_id, 'grouped', now(), 45, :stale, now(), now(), now())
                """), 
                {"id": s_id, "c_id": class_id, "comp_id": comp_id, "stale": stale}
            )
        
        # Create Groups with valid 002+ 'reason' field
        g_a, g_b, g_c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        for s_id, g_id in [(sess_a, g_a), (sess_b, g_b), (sess_c, g_c)]:
            conn.execute(
                text("""
                    INSERT INTO learning_groups (id, session_id, name, group_type, reason, sort_order) 
                    VALUES (:id, :s_id, 'Group', 'extension', 'Migration test group', 0)
                """), 
                {"id": g_id, "s_id": s_id}
            )
        
        # Create Memberships
        # Case A: 3 memberships
        for i in range(3):
            s_id = str(uuid.uuid4())
            conn.execute(
                text("INSERT INTO students (id, classroom_id, name, grade) VALUES (:id, :c_id, :name, 1)"), 
                {"id": s_id, "c_id": class_id, "name": f"S{i}"}
            )
            conn.execute(
                text("INSERT INTO group_memberships (id, session_id, group_id, student_id, original_group_type, assignment_reason) VALUES (:id, :s_id, :g_id, :stu_id, 'extension', 'r')"), 
                {"id": str(uuid.uuid4()), "s_id": sess_a, "g_id": g_a, "stu_id": s_id}
            )
            
        # Case B: 1 membership
        s_b_id = str(uuid.uuid4())
        conn.execute(
            text("INSERT INTO students (id, classroom_id, name, grade) VALUES (:id, :c_id, :name, 1)"), 
            {"id": s_b_id, "c_id": class_id, "name": "SB"}
        )
        conn.execute(
            text("INSERT INTO group_memberships (id, session_id, group_id, student_id, original_group_type, assignment_reason) VALUES (:id, :s_id, :g_id, :stu_id, 'extension', 'r')"), 
            {"id": str(uuid.uuid4()), "s_id": sess_b, "g_id": g_b, "stu_id": s_b_id}
        )
        
        # Case C: 0 memberships
        
        # Insert 004 Priorities explicitly lacking 'student_count_at_generation'
        for s_id, g_id in [(sess_a, g_a), (sess_b, g_b), (sess_c, g_c)]:
            conn.execute(
                text("""
                    INSERT INTO group_priorities (
                        id, session_id, group_id, priority_score, priority_rank, priority_tier,
                        instructional_need_score, evidence_severity_score, uncertainty_score,
                        missed_instruction_score, group_complexity_score, reach_score,
                        factor_breakdown, reasons, top_reason, created_at, updated_at
                    ) VALUES (
                        :id, :s_id, :g_id, 10, 1, 'low',
                        0, 0, 0, 0, 0, 0, '{}', '[]', 'test', now(), now()
                    )
                """), 
                {"id": str(uuid.uuid4()), "s_id": s_id, "g_id": g_id}
            )
            
    # 5. Upgrade to Revision 005
    command.upgrade(alembic_cfg, "005_priority_hardening")
    
    # 6. Assert Post-Migration State
    with postgres_db_engine.begin() as conn:
        # A. Assert actual Alembic revision
        version_num = conn.execute(text("SELECT version_num FROM alembic_version;")).scalar()
        assert version_num == "005_priority_hardening"
        
        # B. Check column existence (post-005)
        col_exists = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'group_priorities'
              AND column_name = 'student_count_at_generation';
        """)).scalar()
        assert col_exists == 'student_count_at_generation'
        
        # C. Verify Constraint Creation
        constraints = conn.execute(text("""
            SELECT conname 
            FROM pg_constraint 
            WHERE conname IN ('uq_priority_session_rank', 'chk_student_count_gen_positive');
        """)).fetchall()
        constraint_names = {c[0] for c in constraints}
        assert 'uq_priority_session_rank' in constraint_names
        assert 'chk_student_count_gen_positive' in constraint_names
        
        # D. Migration Semantics Execution
        
        # Case A: Valid non-stale preserves priority and exact count = 3
        res_a = conn.execute(
            text("SELECT student_count_at_generation FROM group_priorities WHERE session_id = :sid"), 
            {"sid": sess_a}
        ).fetchall()
        assert len(res_a) == 1
        assert res_a[0][0] == 3
        sess_a_check = conn.execute(
            text("SELECT priority_stale, priority_generated_at FROM class_sessions WHERE id = :sid"), 
            {"sid": sess_a}
        ).fetchone()
        assert sess_a_check[0] is False
        assert sess_a_check[1] is not None
        
        # Case B: Stale plan deletes priorities completely and resets session
        res_b = conn.execute(
            text("SELECT id FROM group_priorities WHERE session_id = :sid"), 
            {"sid": sess_b}
        ).fetchall()
        assert len(res_b) == 0
        sess_b_check = conn.execute(
            text("SELECT priority_stale, priority_generated_at FROM class_sessions WHERE id = :sid"), 
            {"sid": sess_b}
        ).fetchone()
        assert sess_b_check[0] is False
        assert sess_b_check[1] is None
        
        # Case C: Empty group deletes priorities completely and resets session
        res_c = conn.execute(
            text("SELECT id FROM group_priorities WHERE session_id = :sid"), 
            {"sid": sess_c}
        ).fetchall()
        assert len(res_c) == 0
        sess_c_check = conn.execute(
            text("SELECT priority_stale, priority_generated_at FROM class_sessions WHERE id = :sid"), 
            {"sid": sess_c}
        ).fetchone()
        assert sess_c_check[0] is False
        assert sess_c_check[1] is None
