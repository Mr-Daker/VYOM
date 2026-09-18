"""curriculum knowledge base

Revision ID: 007_curriculum_knowledge_base
Revises: 006_rotation_scheduler
Create Date: 2026-09-17 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007_curriculum_knowledge_base'
down_revision = '006_rotation_scheduler'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.engine.name == 'postgresql'

    if is_postgres:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector;')

    op.create_table(
        'curriculum_documents',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('source_name', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('grade_min', sa.Integer(), nullable=True),
        sa.Column('grade_max', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('checksum', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('embedding_status', sa.String(), nullable=False),
        sa.Column('original_filename', sa.String(), nullable=True),
        sa.Column('mime_type', sa.String(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('checksum', name='uq_curr_doc_checksum'),
        sa.CheckConstraint('grade_min >= 1', name='chk_curr_doc_grade_min'),
        sa.CheckConstraint('grade_max >= 1', name='chk_curr_doc_grade_max'),
        sa.CheckConstraint('grade_min <= grade_max', name='chk_curr_doc_grade_order'),
        sa.CheckConstraint("source_type IN ('teacher_upload', 'curriculum_framework', 'textbook', 'teacher_guide', 'reference')", name="chk_curr_doc_source_type"),
        sa.CheckConstraint("status IN ('draft', 'processing', 'ready', 'failed', 'archived')", name="chk_curr_doc_status"),
        sa.CheckConstraint("embedding_status IN ('not_requested', 'pending', 'ready', 'failed')", name="chk_curr_doc_embedding_status"),
    )

    op.create_table(
        'curriculum_chunks',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', sa.UUID(as_uuid=True), sa.ForeignKey('curriculum_documents.id'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('text_hash', sa.String(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('section_title', sa.String(), nullable=True),
        sa.Column('embedding', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_curr_chunk_doc_idx'),
        sa.CheckConstraint('chunk_index >= 0', name='chk_curr_chunk_idx_pos'),
        sa.CheckConstraint("length(trim(text)) > 0", name='chk_curr_chunk_text_nonblank'),
        sa.CheckConstraint("page_start IS NULL OR page_start >= 1", name="chk_curr_chunk_page_start"),
        sa.CheckConstraint("page_end IS NULL OR page_end >= 1", name="chk_curr_chunk_page_end"),
        sa.CheckConstraint("page_start IS NULL OR page_end IS NULL OR page_start <= page_end", name="chk_curr_chunk_page_order"),
    )

    if is_postgres:
        from app.core.curriculum_config import CURRICULUM_EMBEDDING_DIMENSION
        op.execute(f'ALTER TABLE curriculum_chunks ALTER COLUMN embedding TYPE vector({CURRICULUM_EMBEDDING_DIMENSION}) USING embedding::vector;')

    op.create_table(
        'curriculum_chunk_competencies',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('chunk_id', sa.UUID(as_uuid=True), sa.ForeignKey('curriculum_chunks.id'), nullable=False),
        sa.Column('competency_id', sa.UUID(as_uuid=True), sa.ForeignKey('competencies.id'), nullable=False),
        sa.Column('mapping_type', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('chunk_id', 'competency_id', name='uq_curr_map_chunk_comp'),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='chk_curr_map_confidence'),
        sa.CheckConstraint("mapping_type IN ('manual', 'metadata', 'rule_based', 'semantic')", name="chk_curr_map_type"),
    )


def downgrade() -> None:
    op.drop_table('curriculum_chunk_competencies')
    op.drop_table('curriculum_chunks')
    op.drop_table('curriculum_documents')
