import pytest
pytestmark = pytest.mark.postgres

import pytest
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency, Competency

@pytest.fixture
def curriculum_postgres_db(postgres_db_engine, monkeypatch):
    from alembic.config import Config
    from alembic import command
    from app.core.config import settings

    assert postgres_db_engine.url.database.endswith("_test")

    # Explicitly wire up the test DB url
    url = postgres_db_engine.url.render_as_string(hide_password=False)
    monkeypatch.setattr(settings, "DATABASE_URL", url)

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", url)

    with postgres_db_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
        
        # Verify db matches
        res = conn.execute(text("SELECT current_database();"))
        assert res.scalar() == postgres_db_engine.url.database

    command.upgrade(alembic_cfg, "007_curriculum_knowledge_base")

    with postgres_db_engine.connect() as conn:
        res = conn.execute(text("SELECT version_num FROM alembic_version;"))
        version = res.scalar()
        assert version == "007_curriculum_knowledge_base"

    yield postgres_db_engine

def test_pg_migration_names_match(curriculum_postgres_db):
    from sqlalchemy import text
    with curriculum_postgres_db.connect() as conn:
        res = conn.execute(text("SELECT conname FROM pg_constraint"))
        constraints = [row[0] for row in res]
        expected = [
            'uq_curr_doc_checksum', 'chk_curr_doc_grade_min', 'chk_curr_doc_grade_max', 'chk_curr_doc_grade_order',
            'uq_curr_chunk_doc_idx', 'chk_curr_chunk_idx_pos', 'chk_curr_chunk_text_nonblank',
            'uq_curr_map_chunk_comp', 'chk_curr_map_confidence',
            'chk_curr_doc_source_type', 'chk_curr_doc_status', 'chk_curr_doc_embedding_status',
            'chk_curr_map_type', 'chk_curr_chunk_page_start', 'chk_curr_chunk_page_end', 'chk_curr_chunk_page_order'
        ]
        for c in expected:
            assert c in constraints

def test_pgvector_extension_and_column(curriculum_postgres_db):
    with curriculum_postgres_db.connect() as conn:
        ext_res = conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector';"))
        assert ext_res.scalar() == 'vector'

        col_res = conn.execute(text(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relname = 'curriculum_chunks' "
            "  AND a.attname = 'embedding' "
            "  AND n.nspname = 'public';"
        )).fetchone()
        
        assert col_res[0] == 'vector(768)'

def test_orm_pgvector_roundtrip_and_distance(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    doc_id = uuid4()
    
    with Session(curriculum_postgres_db) as session:
        doc = CurriculumDocument(id=doc_id, title="T", source_type="reference", source_name="T", subject="math", language="en", version="1", checksum="c1", status="ready", embedding_status="ready")
        session.add(doc)
        session.flush()
        
        v_near = [1.0] + [0.0]*767
        v_far = [-1.0] + [0.0]*767
        
        c_near = CurriculumChunk(id=uuid4(), document_id=doc_id, chunk_index=1, text="Near", text_hash="h1", embedding=v_near)
        c_far = CurriculumChunk(id=uuid4(), document_id=doc_id, chunk_index=2, text="Far", text_hash="h2", embedding=v_far)
        
        session.add(c_near)
        session.add(c_far)
        session.commit()
        
        session.expire_all()
        
        chunk = session.query(CurriculumChunk).filter(CurriculumChunk.id == c_near.id).first()
        assert len(chunk.embedding) == 768
        assert type(chunk.embedding) == list
        assert chunk.embedding[0] == 1.0
        
        c_near_id = c_near.id
        c_far_id = c_far.id

    # Actual Vector query
    with curriculum_postgres_db.connect() as conn:
        v_query = "[1.0, 0.0, " + "0.0, " * 765 + "0.0]"
        res = conn.execute(text(
            f"SELECT id FROM curriculum_chunks ORDER BY embedding <=> '{v_query}'::vector LIMIT 2;"
        )).fetchall()

        assert str(res[0][0]) == str(c_near_id)
        assert str(res[1][0]) == str(c_far_id)


def create_valid_document(session, checksum=None):
    from uuid import uuid4
    from app.models.all_models import CurriculumDocument
    if checksum is None:
        checksum = f"curr-{uuid4()}"

    doc = CurriculumDocument(
        id=uuid4(),
        title="Test document",
        source_type="reference",
        source_name="Test",
        subject="math",
        language="en",
        version="1",
        checksum=checksum,
        status="ready",
        embedding_status="ready",
    )

    session.add(doc)
    session.commit()

    return doc

def create_valid_chunk(session, document_id, index=0):
    c = CurriculumChunk(id=uuid4(), document_id=document_id, chunk_index=index, text=f"T{index}", text_hash=f"T{index}")
    session.add(c)
    session.commit()
    return c

def test_postgresql_constraints_enforced(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        # Document constraints
        
        # uq_curr_doc_checksum
        d_uq = create_valid_document(session, "c_uq")
        d2 = CurriculumDocument(id=uuid4(), title="T", source_type="reference", source_name="T", subject="math", language="en", version="1", checksum="c_uq", status="ready", embedding_status="ready")
        session.add(d2)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "uq_curr_doc_checksum" in str(exc.value)
        session.rollback()
        
        # chk_curr_doc_grade_min
        d3 = CurriculumDocument(id=uuid4(), title="T", source_type="reference", source_name="T", subject="math", language="en", version="1", checksum="c_gmin", status="ready", embedding_status="ready", grade_min=0)
        session.add(d3)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_doc_grade_min" in str(exc.value)
        session.rollback()
        
        # chk_curr_doc_grade_max
        d4 = CurriculumDocument(id=uuid4(), title="T", source_type="reference", source_name="T", subject="math", language="en", version="1", checksum="c_gmax", status="ready", embedding_status="ready", grade_max=0)
        session.add(d4)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_doc_grade_max" in str(exc.value)
        session.rollback()
        
        # chk_curr_doc_grade_order
        d5 = CurriculumDocument(id=uuid4(), title="T", source_type="reference", source_name="T", subject="math", language="en", version="1", checksum="c_gord", status="ready", embedding_status="ready", grade_min=3, grade_max=2)
        session.add(d5)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_doc_grade_order" in str(exc.value)
        session.rollback()
        
        # Chunk constraints
        doc_valid = create_valid_document(session, "c_chunk_test")
        
        # chk_curr_chunk_idx_pos
        c_idx = CurriculumChunk(id=uuid4(), document_id=doc_valid.id, chunk_index=-1, text="T", text_hash="h1")
        session.add(c_idx)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_chunk_idx_pos" in str(exc.value)
        session.rollback()

        # chk_curr_chunk_text_nonblank
        c_blk = CurriculumChunk(id=uuid4(), document_id=doc_valid.id, chunk_index=1, text="   ", text_hash="h2")
        session.add(c_blk)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_chunk_text_nonblank" in str(exc.value)
        session.rollback()

        # uq_curr_chunk_doc_idx
        create_valid_chunk(session, doc_valid.id, 99)
        c_dup = CurriculumChunk(id=uuid4(), document_id=doc_valid.id, chunk_index=99, text="T2", text_hash="h3")
        session.add(c_dup)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "uq_curr_chunk_doc_idx" in str(exc.value)
        session.rollback()
        
        # Mapping constraints
        chunk_valid = create_valid_chunk(session, doc_valid.id, 100)
        comp = Competency(id=uuid4(), code="T-MAP-C", name="T", subject="math")
        session.add(comp)
        session.commit()
        
        m1 = CurriculumChunkCompetency(chunk_id=chunk_valid.id, competency_id=comp.id, mapping_type="manual")
        session.add(m1)
        session.commit()
        
        # uq_curr_map_chunk_comp
        m2 = CurriculumChunkCompetency(chunk_id=chunk_valid.id, competency_id=comp.id, mapping_type="metadata")
        session.add(m2)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "uq_curr_map_chunk_comp" in str(exc.value)
        session.rollback()
        
        comp2 = Competency(id=uuid4(), code="T-MAP-C2", name="T", subject="math")
        session.add(comp2)
        session.commit()
        
        # chk_curr_map_confidence < 0
        m3 = CurriculumChunkCompetency(chunk_id=chunk_valid.id, competency_id=comp2.id, mapping_type="semantic", confidence=-0.01)
        session.add(m3)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_map_confidence" in str(exc.value)
        session.rollback()
        
        # chk_curr_map_confidence > 1
        m4 = CurriculumChunkCompetency(chunk_id=chunk_valid.id, competency_id=comp2.id, mapping_type="semantic", confidence=1.01)
        session.add(m4)
        with pytest.raises(IntegrityError) as exc:
            session.flush()
        assert "chk_curr_map_confidence" in str(exc.value)
        session.rollback()


def test_postgres_chk_curr_doc_source_type(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumDocument
        from uuid import uuid4
        doc = CurriculumDocument(id=uuid4(), title="A", source_type="invalid_type", source_name="R", subject="math", language="en", version="1", checksum=f"C-PG-{uuid4()}", status="ready", embedding_status="ready")
        session.add(doc)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_doc_source_type" in str(e)

def test_postgres_chk_curr_doc_status(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumDocument
        from uuid import uuid4
        doc = CurriculumDocument(id=uuid4(), title="A", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-PG-{uuid4()}", status="invalid_status", embedding_status="ready")
        session.add(doc)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_doc_status" in str(e)

def test_postgres_chk_curr_doc_embedding_status(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumDocument
        from uuid import uuid4
        doc = CurriculumDocument(id=uuid4(), title="A", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-PG-{uuid4()}", status="ready", embedding_status="invalid_emb")
        session.add(doc)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_doc_embedding_status" in str(e)

def test_postgres_chk_curr_chunk_page_start(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumChunk
        from uuid import uuid4
        doc = create_valid_document(session)
        chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A", text_hash=str(uuid4()), page_start=0)
        session.add(chunk)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_chunk_page_start" in str(e)

def test_postgres_chk_curr_chunk_page_end(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumChunk
        from uuid import uuid4
        doc = create_valid_document(session)
        chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A", text_hash=str(uuid4()), page_start=None, page_end=0)
        session.add(chunk)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_chunk_page_end" in str(e)

def test_postgres_chk_curr_chunk_page_order(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumChunk
        from uuid import uuid4
        doc = create_valid_document(session)
        chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A", text_hash=str(uuid4()), page_start=10, page_end=9)
        session.add(chunk)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_chunk_page_order" in str(e)

def test_postgres_chk_curr_map_type(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    with Session(curriculum_postgres_db) as session:
        import sqlalchemy as sa
        from app.models.all_models import CurriculumChunkCompetency, Competency
        from uuid import uuid4
        comp = Competency(code=f"T-PG-{uuid4()}", name="A", subject="math")
        session.add(comp)
        session.commit()
        doc = create_valid_document(session)
        chunk = create_valid_chunk(session, doc.id, 0)
    
        m = CurriculumChunkCompetency(chunk_id=chunk.id, competency_id=comp.id, mapping_type="invalid_map")
        session.add(m)
        try:
            session.flush()
            assert False, "Should raise IntegrityError"
        except sa.exc.IntegrityError as e:
            session.rollback()
            assert "chk_curr_map_type" in str(e)

def test_postgres_chk_curr_chunk_page_equality(curriculum_postgres_db):
    from sqlalchemy.orm import Session
    from app.models.all_models import CurriculumChunk
    from uuid import uuid4
    with Session(curriculum_postgres_db) as session:
        doc = create_valid_document(session)
        chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A", text_hash=str(uuid4()), page_start=10, page_end=10)
        session.add(chunk)
        session.flush()
