"""Priority hardening

Revision ID: 005_priority_hardening
Revises: 004_teacher_priority
Create Date: 2026-09-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_priority_hardening'
down_revision = '004_teacher_priority'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Add student_count_at_generation nullable
    op.add_column('group_priorities', sa.Column('student_count_at_generation', sa.Integer(), nullable=True))
    
    # 2. Identify sessions containing any priority row whose group has no current members,
    # OR where the priority is stale (meaning current membership may not match generation membership).
    op.execute("""
        CREATE TEMP TABLE invalid_priority_sessions AS
        
        SELECT DISTINCT cs.id AS session_id
        FROM class_sessions cs
        JOIN group_priorities gp
            ON gp.session_id = cs.id
        WHERE cs.priority_stale = TRUE
        
        UNION
        
        SELECT DISTINCT gp.session_id
        FROM group_priorities gp
        LEFT JOIN group_memberships gm
            ON gm.group_id = gp.group_id
        GROUP BY gp.session_id, gp.id
        HAVING COUNT(gm.id) = 0
    """)
    
    # 3. Delete entire priority plan for affected sessions
    op.execute("""
        DELETE FROM group_priorities
        WHERE session_id IN (SELECT session_id FROM invalid_priority_sessions)
    """)
    
    # 4. Reset those sessions
    op.execute("""
        UPDATE class_sessions
        SET priority_generated_at = NULL,
            priority_stale = FALSE
        WHERE id IN (SELECT session_id FROM invalid_priority_sessions)
    """)
    
    # 5. Drop temp table
    op.execute("DROP TABLE invalid_priority_sessions")
    
    # 6. Backfill exact current membership count for old priority rows.
    # INVARIANT: priority_stale = false -> grouping has not changed since the priority was generated
    # -> current membership count is a valid generation-count backfill.
    op.execute("""
        UPDATE group_priorities gp
        SET student_count_at_generation = counts.cnt
        FROM (
            SELECT group_id, COUNT(*) AS cnt
            FROM group_memberships
            GROUP BY group_id
        ) counts
        WHERE counts.group_id = gp.group_id
    """)
    
    # 7. Apply NOT NULL and constraints
    with op.batch_alter_table('group_priorities', schema=None) as batch_op:
        batch_op.alter_column('student_count_at_generation', nullable=False)
        batch_op.create_check_constraint(
            "chk_student_count_gen_positive",
            "student_count_at_generation > 0"
        )
        batch_op.create_unique_constraint('uq_priority_session_rank', ['session_id', 'priority_rank'])

def downgrade() -> None:
    with op.batch_alter_table('group_priorities', schema=None) as batch_op:
        batch_op.drop_constraint('uq_priority_session_rank', type_='unique')
        batch_op.drop_constraint('chk_student_count_gen_positive', type_='check')
        batch_op.drop_column('student_count_at_generation')

