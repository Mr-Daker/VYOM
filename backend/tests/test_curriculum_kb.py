import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

import math

def unit_vector_768():
    return [1.0, 0.0, *([0.0] * 766)]

def vector_with_cosine(cosine_value: float):
    return [cosine_value, math.sqrt(1.0 - cosine_value ** 2), *([0.0] * 766)]

def test_vector_helpers():
    assert len(unit_vector_768()) == 768
    assert len(vector_with_cosine(0.6)) == 768

from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency, Competency, ClassSession, RotationPlan
from app.services.text_processor import normalize_text, hash_text, chunk_text
from app.services.curriculum_retrieval import lexical_similarity, cosine_similarity
from app.core.exceptions import CurriculumDocumentDuplicateError

from app.api.main import app
from app.api.routes.curriculum import get_embedding_provider
from app.services.embedding import FakeEmbeddingProvider

class FailingEmbeddingProvider:
    def embed_texts(self, texts):
        raise RuntimeError("provider unavailable")

@pytest.fixture(autouse=True)
def override_embedding_provider():
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    yield
    app.dependency_overrides.clear()



def test_normalization_deterministic():
    text1 = "Addition\r\n\r\nBasics  here"
    text2 = "Addition\n\nBasics here"
    assert normalize_text(text1) == normalize_text(text2)
    assert hash_text(normalize_text(text1)) == hash_text(normalize_text(text2))

def test_normalization_duplicate_checksum():
    text1 = "Hello\r\n\r\nWorld"
    text2 = "Hello\n\nWorld"
    assert hash_text(normalize_text(text1)) == hash_text(normalize_text(text2))

def test_chunking_deterministic():
    text = "Para 1\n\nPara 2\n\nPara 3"
    chunks1 = chunk_text(text)
    chunks2 = chunk_text(text)
    assert len(chunks1) == len(chunks2)
    assert chunks1 == chunks2
    assert [hash_text(c) for c in chunks1] == [hash_text(c) for c in chunks2]

def test_chunk_max_bound():
    text = "A" * 2000
    chunks = chunk_text(text)
    # Target max is 1800
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= 1800

def test_overlap_bound():
    text = "A" * 2000
    chunks = chunk_text(text)
    # Check if there is overlap
    assert len(chunks) == 2

def test_empty_content_rejected(client, db_session):
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "T", "source_type": "reference", "source_name": "T", "subject": "T",
        "language": "en", "version": "1.0", "content": "   "
    })
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "CURRICULUM_CONTENT_EMPTY"

def test_oversized_content_rejected(client, db_session):
    # max is 5MB
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "T", "source_type": "reference", "source_name": "T", "subject": "T",
        "language": "en", "version": "1.0", "content": "A" * (5*1024*1024 + 1)
    })
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "CURRICULUM_CONTENT_TOO_LARGE"

def test_valid_document_ingestion(client, db_session):
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Grade 2 Math Guide", "source_type": "teacher_guide",
        "source_name": "School Resource", "subject": "math",
        "grade_min": 2, "grade_max": 2, "language": "en",
        "version": "1.0", "content": "addition and subtraction"
    })
    assert res.status_code == 201
    assert res.json()["title"] == "Grade 2 Math Guide"
    assert res.json()["status"] == "ready"
    assert res.json()["embedding_status"] == "ready"
    assert res.json()["chunk_count"] == 1

def test_duplicate_ingestion(client, db_session):
    payload = {
        "title": "Dup Test", "source_type": "test", "source_name": "test",
        "subject": "math", "language": "en", "version": "1.0",
        "content": "This is a duplicate test."
    }
    client.post("/api/v1/curriculum/documents", json=payload)
    res = client.post("/api/v1/curriculum/documents", json=payload)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CURRICULUM_DOCUMENT_DUPLICATE"

def test_different_version_content_allowed(client, db_session):
    p1 = {
        "title": "V1", "source_type": "test", "source_name": "test",
        "subject": "math", "language": "en", "version": "1.0",
        "content": "Content 1"
    }
    p2 = {
        "title": "V2", "source_type": "test", "source_name": "test",
        "subject": "math", "language": "en", "version": "2.0",
        "content": "Content 2"
    }
    r1 = client.post("/api/v1/curriculum/documents", json=p1)
    r2 = client.post("/api/v1/curriculum/documents", json=p2)
    assert r1.status_code == 201
    assert r2.status_code == 201

def test_document_listing_filtering(client, db_session):
    client.post("/api/v1/curriculum/documents", json={
        "title": "A", "source_type": "A", "source_name": "A", "subject": "math",
        "language": "en", "version": "1.0", "content": "AA", "grade_min": 2, "grade_max": 2
    })
    client.post("/api/v1/curriculum/documents", json={
        "title": "B", "source_type": "B", "source_name": "B", "subject": "science",
        "language": "ta", "version": "1.0", "content": "BB", "grade_min": 3, "grade_max": 3
    })
    r1 = client.get("/api/v1/curriculum/documents?subject=math")
    assert r1.json()["total"] >= 1
    
    r2 = client.get("/api/v1/curriculum/documents?language=TA")
    assert r2.json()["total"] >= 1
    
    r3 = client.get("/api/v1/curriculum/documents?grade=2")
    assert r3.json()["total"] >= 1

def test_document_get_and_archive(client, db_session):
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Archive Test", "source_type": "A", "source_name": "A", "subject": "S",
        "language": "en", "version": "1.0", "content": "Archive content"
    })
    doc_id = res.json()["id"]
    
    get_res = client.get(f"/api/v1/curriculum/documents/{doc_id}")
    assert get_res.json()["status"] == "ready"
    
    arch_res = client.post(f"/api/v1/curriculum/documents/{doc_id}/archive")
    assert arch_res.json()["status"] == "archived"

def test_manual_competency_mapping(client, db_session):
    comp = Competency(code="TEST-1", name="Test", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "T", "source_type": "reference", "source_name": "T", "subject": "S",
        "language": "en", "version": "1.0", "content": "Test content mapping"
    })
    doc_id = res.json()["id"]
    
    chunks = client.get(f"/api/v1/curriculum/documents/{doc_id}/chunks").json()["items"]
    chunk_id = chunks[0]["id"]
    
    map_res = client.post(f"/api/v1/curriculum/chunks/{chunk_id}/competencies", json={
        "competency_ids": [str(comp.id)],
        "mapping_type": "manual"
    })
    assert map_res.status_code == 200

def test_mapping_missing_competency_atomic_failure(client, db_session):
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "T2", "source_type": "T2", "source_name": "T2", "subject": "S",
        "language": "en", "version": "1.0", "content": "Test content mapping missing"
    })
    doc_id = res.json()["id"]
    chunks = client.get(f"/api/v1/curriculum/documents/{doc_id}/chunks").json()["items"]
    chunk_id = chunks[0]["id"]
    
    map_res = client.post(f"/api/v1/curriculum/chunks/{chunk_id}/competencies", json={
        "competency_ids": [str(uuid4()), str(uuid4())],
        "mapping_type": "manual"
    })
    assert map_res.status_code == 400
    assert map_res.json()["error"]["code"] == "CURRICULUM_MAPPING_INVALID"

def test_hybrid_retrieval_and_provenance(client, db_session):
    comp = Competency(code="ADD-2", name="Two-digit addition", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    # Document A
    doc_a = client.post("/api/v1/curriculum/documents", json={
        "title": "Grade 2 Mathematics Teacher Guide", "source_type": "textbook",
        "source_name": "NCERT", "subject": "math", "grade_min": 2, "grade_max": 2,
        "language": "en", "version": "1.0",
        "content": "place value two-digit addition regrouping worked examples"
    }).json()
    
    # Document B
    doc_b = client.post("/api/v1/curriculum/documents", json={
        "title": "Unrelated Science Notes", "source_type": "textbook",
        "source_name": "NCERT", "subject": "science", "grade_min": 2, "grade_max": 2,
        "language": "en", "version": "1.0",
        "content": "plants and soil"
    }).json()
    
    chunk_a = client.get(f"/api/v1/curriculum/documents/{doc_a['id']}/chunks").json()["items"][0]["id"]
    client.post(f"/api/v1/curriculum/chunks/{chunk_a}/competencies", json={
        "competency_ids": [str(comp.id)],
        "mapping_type": "manual"
    })
    
    # Retrieval
    res = client.post("/api/v1/curriculum/retrieve", json={
        "competency_id": str(comp.id),
        "query_text": "two digit addition regrouping",
        "grade": 2,
        "language": "en"
    })
    
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) >= 1
    top = data["results"][0]
    
    # Document A chunk ranks above Document B
    assert top["source"]["document_id"] == doc_a["id"]
    assert top["source"]["title"] == "Grade 2 Mathematics Teacher Guide"
    assert top["source"]["version"] == "1.0"
    
    # competency score > 0
    assert top["scores"]["competency"] > 0
    # lexical score > unrelated result
    assert top["scores"]["lexical"] > 0
    
    # provenance complete
    assert top["chunk_id"] == chunk_a

def test_archive_excluded_from_retrieval(client, db_session):
    comp = Competency(code="TEST-ARCHIVE", name="Archive", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    doc = client.post("/api/v1/curriculum/documents", json={
        "title": "Archive Retrieval Test", "source_type": "A", "source_name": "A",
        "subject": "math", "language": "en", "version": "1.0", "content": "Archived content for test"
    }).json()
    
    client.post(f"/api/v1/curriculum/documents/{doc['id']}/archive")
    
    res = client.post("/api/v1/curriculum/retrieve", json={
        "competency_id": str(comp.id),
        "query_text": "Archived content for test"
    })
    for r in res.json()["results"]:
        assert r["source"]["document_id"] != doc["id"]

def test_hybrid_weight_renormalization_and_lexical(client, db_session):
    # Without semantic search, weights renormalize
    comp = Competency(code="TEST-RENORM", name="Renorm", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={
        "competency_id": str(comp.id),
        "query_text": "test"
    })
    # Since semantic is fake, it's used
    assert res.json()["semantic_search_used"] == True



def test_embedding_retry(client, db_session):
    app.dependency_overrides[get_embedding_provider] = lambda: FailingEmbeddingProvider()
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Retry Test", "source_type": "reference", "source_name": "T",
        "subject": "math", "language": "en", "version": "1.0", "content": "Content to retry embeddings on."
    })
    doc_id = res.json()["id"]
    assert res.json()["embedding_status"] == "failed"
    
    # Verify chunks have no embeddings
    from app.models.all_models import CurriculumChunk
    c = db_session.query(CurriculumChunk).filter(CurriculumChunk.document_id == doc_id).first()
    assert c.embedding is None
    
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbeddingProvider()
    retry_res = client.post(f"/api/v1/curriculum/documents/{doc_id}/embed")
    assert retry_res.status_code == 200
    assert retry_res.json()["embedding_status"] == "ready"
    
    db_session.expire_all()
    c2 = db_session.query(CurriculumChunk).filter(CurriculumChunk.document_id == doc_id).first()
    assert c2.embedding is not None    

def test_exception_contract_envelope(client, db_session):
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "T", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": "   "
    })
    assert res.status_code == 400
    # ensure it's a string code
    assert isinstance(res.json()["error"]["code"], str)
    assert res.json()["error"]["code"] == "CURRICULUM_CONTENT_EMPTY"
    
    # Check duplicate
    payload = {
        "title": "Dup", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": "Dup Content"
    }
    client.post("/api/v1/curriculum/documents", json=payload)
    dup = client.post("/api/v1/curriculum/documents", json=payload)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "CURRICULUM_DOCUMENT_DUPLICATE"
    
    # Check unknown
    unk = client.get(f"/api/v1/curriculum/documents/{uuid4()}")
    assert unk.status_code == 404
    assert unk.json()["error"]["code"] == "CURRICULUM_DOCUMENT_NOT_FOUND"

def test_semantic_fallback_failing_provider(client, db_session):
    app.dependency_overrides[get_embedding_provider] = lambda: FailingEmbeddingProvider()
    comp = Competency(code="TEST-FAIL-PROV", name="FailProv", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    doc = client.post("/api/v1/curriculum/documents", json={
        "title": "Failing", "source_type": "A", "source_name": "A",
        "subject": "math", "language": "en", "version": "1.0", "content": "Fallback content test"
    }).json()
    assert doc["embedding_status"] == "failed"
    
    res = client.post("/api/v1/curriculum/retrieve", json={
        "competency_id": str(comp.id),
        "query_text": "Fallback content test"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["semantic_search_used"] == False
    assert len(data["results"]) > 0
    assert data["results"][0]["scores"]["semantic"] is None

def test_semantic_fallback_none_provider(client, db_session):
    app.dependency_overrides[get_embedding_provider] = lambda: None
    comp = Competency(code="TEST-NONE-PROV", name="NoneProv", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    doc = client.post("/api/v1/curriculum/documents", json={
        "title": "None", "source_type": "A", "source_name": "A",
        "subject": "math", "language": "en", "version": "1.0", "content": "None content test"
    }).json()
    assert doc["embedding_status"] == "not_requested"
    assert doc["chunk_count"] == 1
    
    res = client.post("/api/v1/curriculum/retrieve", json={
        "competency_id": str(comp.id),
        "query_text": "None content test"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["semantic_search_used"] == False

def test_ingestion_rollback_after_flushed(client, db_session, monkeypatch):
    from app.services.curriculum_ingestion import CurriculumChunkRepository
    original_add = CurriculumChunkRepository.add
    call_count = [0]
    
    def mocked_add(self, chunk):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("Injected failure during second chunk add")
        original_add(self, chunk)
        
    monkeypatch.setattr(CurriculumChunkRepository, "add", mocked_add)
    
    payload = {
        "title": "Rollback", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": "Chunk 1 \n\n Chunk 2"
    }
    res = client.post("/api/v1/curriculum/documents", json=payload)
    assert res.status_code == 500
    
    # Assert DB is empty
    from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
    assert db_session.query(CurriculumDocument).filter(CurriculumDocument.title == "Rollback").count() == 0

def test_real_session_preservation_fixture(client, db_session):
    from app.models.all_models import User, Student, Classroom, ClassSession, Competency, LearningGroup, GroupMembership, GroupPriority, RotationPlan, RotationSlot
    from app.models.enums import UserRole, SessionStatus, GroupType, RotationSlotType
    
    teacher = User(name="Teacher", email=f"t-{uuid4()}@example.com", password_hash="test", role=UserRole.TEACHER)
    db_session.add(teacher)
    db_session.flush()
    
    cr = Classroom(teacher_id=teacher.id, name="CR", default_duration_minutes=45, max_groups=4)
    db_session.add(cr)
    db_session.flush()
    
    student = Student(classroom_id=cr.id, name="Student", grade=1)
    comp = Competency(code=f"T-SESS-{uuid4()}", name="Addition", subject="math", grade=1)
    db_session.add_all([student, comp])
    db_session.flush()
    
    sess = ClassSession(classroom_id=cr.id, target_competency_id=comp.id, status=SessionStatus.SCHEDULED, duration_minutes=45)
    db_session.add(sess)
    db_session.flush()
    
    grp = LearningGroup(session_id=sess.id, name="Check - Addition", group_type=GroupType.CHECK, focus_competency_id=comp.id, reason="Learner needs a readiness check.", mixed_needs=False, teacher_modified=False, sort_order=0)
    db_session.add(grp)
    db_session.flush()
    
    gm = GroupMembership(session_id=sess.id, group_id=grp.id, student_id=student.id, focus_competency_id=comp.id, assignment_reason="Synthetic preservation fixture.", original_group_type=GroupType.CHECK, original_check_mode=None)
    db_session.add(gm)
    
    factor_breakdown = {
        "instructional_need": {"raw": 0.10, "weight": 35, "contribution": 3.5},
        "evidence_severity": {"raw": 0.10, "weight": 25, "contribution": 2.5},
        "uncertainty": {"raw": 0.10, "weight": 15, "contribution": 1.5},
        "missed_instruction": {"raw": 0.10, "weight": 10, "contribution": 1.0},
        "group_complexity": {"raw": 0.10, "weight": 10, "contribution": 1.0},
        "reach": {"raw": 0.10, "weight": 5, "contribution": 0.5},
    }
    
    p = GroupPriority(session_id=sess.id, group_id=grp.id, priority_score=10.0, priority_rank=1, priority_tier="low", teacher_rank=None, instructional_need_score=3.5, evidence_severity_score=2.5, uncertainty_score=1.5, missed_instruction_score=1.0, group_complexity_score=1.0, reach_score=0.5, factor_breakdown=factor_breakdown, reasons=["Synthetic Part 4 preservation fixture."], top_reason="instructional_need", student_count_at_generation=1)
    db_session.add(p)
    
    rp = RotationPlan(session_id=sess.id, session_duration_minutes=45, opening_minutes=3, closing_minutes=2, transition_minutes_each=1, transition_total_minutes=0, teacher_attention_budget_minutes=40, minimum_group_attention_minutes=3, group_count=1, algorithm_version="v1")
    db_session.add(rp)
    db_session.flush()
    
    rs1 = RotationSlot(rotation_plan_id=rp.id, session_id=sess.id, sequence_index=0, slot_type=RotationSlotType.WHOLE_CLASS_OPENING, start_minute=0, end_minute=3, duration_minutes=3)
    rs2 = RotationSlot(rotation_plan_id=rp.id, session_id=sess.id, sequence_index=1, slot_type=RotationSlotType.GROUP_VISIT, group_id=grp.id, start_minute=3, end_minute=43, duration_minutes=40, group_name_snapshot=grp.name, group_type_snapshot=GroupType.CHECK.value, priority_score_snapshot=10.0, algorithm_priority_rank_snapshot=1, teacher_rank_snapshot=None, effective_rank_snapshot=1, student_count_snapshot=1, base_minutes=3, weighted_extra_minutes=37, reason="Guaranteed 3 minutes plus 37 weighted minutes.")
    rs3 = RotationSlot(rotation_plan_id=rp.id, session_id=sess.id, sequence_index=2, slot_type=RotationSlotType.WHOLE_CLASS_CLOSING, start_minute=43, end_minute=45, duration_minutes=2)
    db_session.add_all([rs1, rs2, rs3])
    db_session.flush()
    db_session.commit()
    
    before_status = sess.status
    before_groups = [g.id for g in db_session.query(LearningGroup).filter_by(session_id=sess.id).all()]
    before_memberships = [m.id for m in db_session.query(GroupMembership).filter_by(session_id=sess.id).all()]
    p_row = db_session.query(GroupPriority).filter_by(session_id=sess.id).first()
    before_priority = (p_row.id, p_row.priority_score, p_row.priority_rank, p_row.teacher_rank)
    before_rp = db_session.query(RotationPlan).filter_by(session_id=sess.id).first().id
    before_slots = [s.id for s in db_session.query(RotationSlot).filter_by(session_id=sess.id).order_by(RotationSlot.sequence_index).all()]
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id)})
    assert res.status_code == 200
    
    db_session.expire_all()
    
    s2 = db_session.query(ClassSession).filter_by(id=sess.id).first()
    after_groups = [g.id for g in db_session.query(LearningGroup).filter_by(session_id=sess.id).all()]
    after_memberships = [m.id for m in db_session.query(GroupMembership).filter_by(session_id=sess.id).all()]
    p_row2 = db_session.query(GroupPriority).filter_by(session_id=sess.id).first()
    after_priority = (p_row2.id, p_row2.priority_score, p_row2.priority_rank, p_row2.teacher_rank)
    after_rp = db_session.query(RotationPlan).filter_by(session_id=sess.id).first().id
    after_slots = [s.id for s in db_session.query(RotationSlot).filter_by(session_id=sess.id).order_by(RotationSlot.sequence_index).all()]
    
    assert s2.status == before_status
    assert set(after_groups) == set(before_groups)
    assert set(after_memberships) == set(before_memberships)
    assert after_priority == before_priority
    assert after_rp == before_rp
    assert after_slots == before_slots
    

def test_hybrid_fallback_helper():
    from app.services.curriculum_retrieval import compute_hybrid_score
    # 0.50 / 0.65 = 0.769230... -> * 1.0 = 0.769231
    # 0.15 / 0.65 = 0.230769... -> * 0.50 = 0.115385
    # sum = 0.884616
    score = compute_hybrid_score(1.0, 0.50, None)
    assert round(score, 6) == 0.884615 or round(score, 6) == 0.884616
    
def test_validation_grades_and_metadata(client, db_session):
    # top_k validation
    from app.core.curriculum_config import MAX_RETRIEVAL_TOP_K
    comp = Competency(code="T-GRADE", name="T", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    r1 = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "top_k": 0})
    assert r1.status_code == 422
    r2 = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "top_k": MAX_RETRIEVAL_TOP_K + 1})
    assert r2.status_code == 422
    r_ok = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "top_k": MAX_RETRIEVAL_TOP_K})
    assert r_ok.status_code == 200

    # metadata nonblank
    p1 = {"title": "  ", "source_type": "reference", "source_name": "T", "subject": "math", "language": "en", "version": "1.0", "content": "valid"}
    assert client.post("/api/v1/curriculum/documents", json=p1).status_code == 422
    
    # grades
    p2 = {"title": "T", "source_type": "reference", "source_name": "T", "subject": "math", "language": "en", "version": "1.0", "content": "valid", "grade_min": 0, "grade_max": None}
    assert client.post("/api/v1/curriculum/documents", json=p2).status_code == 422
    p3 = {"title": "T", "source_type": "reference", "source_name": "T", "subject": "math", "language": "en", "version": "1.0", "content": "valid", "grade_min": None, "grade_max": 0}
    assert client.post("/api/v1/curriculum/documents", json=p3).status_code == 422
    p4 = {"title": "T", "source_type": "reference", "source_name": "T", "subject": "math", "language": "en", "version": "1.0", "content": "valid", "grade_min": 3, "grade_max": 2}
    assert client.post("/api/v1/curriculum/documents", json=p4).status_code == 422
    
    # query grade validation
    assert client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "grade": 0}).status_code == 422
    assert client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "language": "  "}).status_code == 422
    assert client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": ""}).status_code == 422


def test_mapping_validation(client, db_session):
    comp = Competency(code="T-MAP", name="T", subject="math")
    db_session.add(comp)
    db_session.commit()
    doc = client.post("/api/v1/curriculum/documents", json={"title": "T", "source_type": "reference", "source_name": "T", "subject": "math", "language": "en", "version": "1.0", "content": "valid"}).json()
    chunks = client.get(f"/api/v1/curriculum/documents/{doc['id']}/chunks").json()["items"]
    chunk_id = chunks[0]["id"]
    
    # manual with confidence -> 422
    r_man = client.post(f"/api/v1/curriculum/chunks/{chunk_id}/competencies", json={"competency_ids": [str(comp.id)], "mapping_type": "manual", "confidence": 1.0})
    assert r_man.status_code == 422
    
    # semantic without confidence -> 422
    r_sem = client.post(f"/api/v1/curriculum/chunks/{chunk_id}/competencies", json={"competency_ids": [str(comp.id)], "mapping_type": "semantic"})
    assert r_sem.status_code == 422
    
    
    # atomic empty mappings
    r_empty = client.post(f"/api/v1/curriculum/chunks/{chunk_id}/competencies", json={"competency_ids": [], "mapping_type": "manual"})
    assert r_empty.status_code == 422
# atomic missing ID
    r_miss = client.post(f"/api/v1/curriculum/chunks/{chunk_id}/competencies", json={"competency_ids": [str(comp.id), str(uuid4())], "mapping_type": "manual"})
    assert r_miss.status_code == 400
    
    from app.models.all_models import CurriculumChunkCompetency
    assert db_session.query(CurriculumChunkCompetency).filter(CurriculumChunkCompetency.chunk_id == chunk_id).count() == 0

def test_embedding_batching(client, db_session, monkeypatch):
    import app.services.curriculum_ingestion
    monkeypatch.setattr(app.services.curriculum_ingestion, "EMBEDDING_BATCH_SIZE", 2)
    
    class CountingProvider:
        def __init__(self):
            self.call_sizes = []
        def embed_texts(self, texts):
            self.call_sizes.append(len(texts))
            from app.core.curriculum_config import CURRICULUM_EMBEDDING_DIMENSION
            return [[0.1] * CURRICULUM_EMBEDDING_DIMENSION for _ in texts]
            
    p = CountingProvider()
    app.dependency_overrides[get_embedding_provider] = lambda: p
    
    content = ("A" * 1250) + "\n\n" + ("B" * 1250) + "\n\n" + ("C" * 1250)
    # Should be 3 chunks
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Batch", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": content
    })
    assert res.status_code == 201
    assert p.call_sizes == [2, 1]

def run_bad_provider_test(client, db_session, provider, expected_status, expected_code):
    from app.api.routes.curriculum import get_embedding_provider
    app.dependency_overrides[get_embedding_provider] = lambda: provider
    from app.models.all_models import CurriculumDocument, CurriculumChunk
    docs_before = db_session.query(CurriculumDocument).count()
    chunks_before = db_session.query(CurriculumChunk).count()
    
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Bad", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": "Content"
    })
    
    assert res.status_code == expected_status
    assert res.json()["error"]["code"] == expected_code
    assert db_session.query(CurriculumDocument).count() == docs_before
    assert db_session.query(CurriculumChunk).count() == chunks_before

def test_embedding_contract_violation_rolls_back(client, db_session):
    class BadProvDim:
        def embed_texts(self, texts):
            return [[0.1] * 767 for _ in texts]
    run_bad_provider_test(client, db_session, BadProvDim(), 400, "EMBEDDING_DIMENSION_MISMATCH")
    
    class BadProvCountSmall:
        def embed_texts(self, texts):
            return []
    run_bad_provider_test(client, db_session, BadProvCountSmall(), 503, "CURRICULUM_EMBEDDING_FAILED")
    
    class BadProvCountLarge:
        def embed_texts(self, texts):
            return [[0.1]*768, [0.1]*768]
    run_bad_provider_test(client, db_session, BadProvCountLarge(), 503, "CURRICULUM_EMBEDDING_FAILED")

    class BadProvNotSeq:
        def embed_texts(self, texts):
            return "not a list"
    run_bad_provider_test(client, db_session, BadProvNotSeq(), 503, "CURRICULUM_EMBEDDING_FAILED")

    class BadProvElemNotSeq:
        def embed_texts(self, texts):
            return ["not a list"]
    run_bad_provider_test(client, db_session, BadProvElemNotSeq(), 503, "CURRICULUM_EMBEDDING_FAILED")
    
    class BadProvStr:
        def embed_texts(self, texts):
            return [["0.1"] * 768]
    run_bad_provider_test(client, db_session, BadProvStr(), 503, "CURRICULUM_EMBEDDING_FAILED")

    class BadProvNone:
        def embed_texts(self, texts):
            return [[None] * 768]
    run_bad_provider_test(client, db_session, BadProvNone(), 503, "CURRICULUM_EMBEDDING_FAILED")
    
    class BadProvBool:
        def embed_texts(self, texts):
            return [[True] * 768]
    run_bad_provider_test(client, db_session, BadProvBool(), 503, "CURRICULUM_EMBEDDING_FAILED")

    class BadProvNaN:
        def embed_texts(self, texts):
            return [[float("nan")] * 768]
    run_bad_provider_test(client, db_session, BadProvNaN(), 503, "CURRICULUM_EMBEDDING_FAILED")
    
    class BadProvInf:
        def embed_texts(self, texts):
            return [[float("inf")] * 768]
    run_bad_provider_test(client, db_session, BadProvInf(), 503, "CURRICULUM_EMBEDDING_FAILED")
    
    class BadProvMinusInf:
        def embed_texts(self, texts):
            return [[float("-inf")] * 768]
    run_bad_provider_test(client, db_session, BadProvMinusInf(), 503, "CURRICULUM_EMBEDDING_FAILED")

def test_oversized_regression_test(client, db_session):
    from app.core.curriculum_config import MAX_CURRICULUM_TEXT_CHARS
    from app.models.all_models import CurriculumDocument, CurriculumChunk
    
    docs_before = db_session.query(CurriculumDocument).count()
    chunks_before = db_session.query(CurriculumChunk).count()
    
    content = "A" * (MAX_CURRICULUM_TEXT_CHARS + 1)
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Oversized", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": content
    })
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "CURRICULUM_CONTENT_TOO_LARGE"
    
    assert db_session.query(CurriculumDocument).count() == docs_before
    assert db_session.query(CurriculumChunk).count() == chunks_before



def test_query_embedding_contract_violation(client, db_session):
    from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
    from uuid import uuid4
    from app.api.routes.curriculum import get_embedding_provider
    
    comp = Competency(code=f"T-BAD-QUERY-{uuid4()}", name="Addition", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc = CurriculumDocument(id=uuid4(), title="Add", source_type="reference", source_name="T", subject="math", language="en", version="1", checksum="C-ADD", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()
    
    chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="two digit addition regrouping", text_hash="ADD")
    db_session.add(chunk)
    db_session.commit()
    
    m = CurriculumChunkCompetency(chunk_id=chunk.id, competency_id=comp.id, mapping_type="manual")
    db_session.add(m)
    db_session.commit()
    
    def run_q(provider):
        app.dependency_overrides[get_embedding_provider] = lambda: provider
        res = client.post("/api/v1/curriculum/retrieve", json={
            "competency_id": str(comp.id),
            "query_text": "addition regrouping",
            "top_k": 5
        })
        assert res.status_code == 200
        
        data = res.json()
        assert len(data["results"]) >= 1
        assert data["semantic_search_used"] == False
        
        r0 = data["results"][0]
        assert r0["scores"]["semantic"] is None
        assert r0["scores"]["competency"] > 0
        assert r0["scores"]["lexical"] > 0
        assert r0["scores"]["hybrid"] > 0
        
    class B1:
        def embed_texts(self, t): return [[0.1]*767]
    run_q(B1())
    
    class B2:
        def embed_texts(self, t): return [[0.1]*769]
    run_q(B2())
    
    class B3:
        def embed_texts(self, t): return [["str"]*768]
    run_q(B3())
    
    class B4:
        def embed_texts(self, t): return [[None]*768]
    run_q(B4())
    
    class B5:
        def embed_texts(self, t): return [[True]*768]
    run_q(B5())
    
    class B6:
        def embed_texts(self, t): return [[float("nan")]*768]
    run_q(B6())
    
    class B7:
        def embed_texts(self, t): return [[float("inf")]*768]
    run_q(B7())
    
    class B8:
        def embed_texts(self, t): return [[float("-inf")]*768]
    run_q(B8())


def test_fresh_query_persistence(client, db_session):
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Fresh", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": "Fresh content"
    })
    doc_id = res.json()["id"]
    
    db_session.expire_all()
    from app.models.all_models import CurriculumDocument, CurriculumChunk
    doc = db_session.query(CurriculumDocument).filter(CurriculumDocument.id == doc_id).first()
    assert doc is not None
    chunks = db_session.query(CurriculumChunk).filter(CurriculumChunk.document_id == doc_id).all()
    assert len(chunks) == res.json()["chunk_count"]
    for c in chunks:
        assert str(c.document_id) == str(doc_id)

def test_embedding_exception_contract():
    from app.core.exceptions import CurriculumEmbeddingFailedError, EmbeddingDimensionMismatchError
    err = CurriculumEmbeddingFailedError(
        details={
            "reason": "bad vector"
        }
    )
    assert err.code == "CURRICULUM_EMBEDDING_FAILED"
    assert err.status_code == 503
    assert err.details == {
        "reason": "bad vector"
    }

    dim = EmbeddingDimensionMismatchError(
        details={
            "actual": 767,
            "expected": 768,
        }
    )
    assert dim.code == "EMBEDDING_DIMENSION_MISMATCH"
    assert dim.status_code == 400


def test_chunk_metadata_provenance_response(client, db_session):
    from app.models.all_models import CurriculumChunk
    res = client.post("/api/v1/curriculum/documents", json={
        "title": "Metadata", "source_type": "reference", "source_name": "T", "subject": "math",
        "language": "en", "version": "1.0", "content": "Content"
    })
    doc_id = res.json()["id"]
    
    chunk = db_session.query(CurriculumChunk).filter(CurriculumChunk.document_id == doc_id).first()
    chunk.metadata_json = {
        "source_section": "Addition",
        "source_page_label": "42",
    }
    db_session.commit()
    
    chunks_res = client.get(f"/api/v1/curriculum/documents/{doc_id}/chunks")
    assert chunks_res.status_code == 200
    chunk_item = chunks_res.json()["items"][0]
    assert chunk_item["metadata_json"] == {
        "source_section": "Addition",
        "source_page_label": "42",
    }

def test_semantic_relevance_scale():
    from app.services.curriculum_retrieval import semantic_relevance
    assert semantic_relevance([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert semantic_relevance([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert semantic_relevance([1.0, 0.0], [-1.0, 0.0]) == 0.0

def test_empty_retrieval(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-EMPTY-{uuid4()}", name="Addition", subject="math")
    db_session.add(comp)
    db_session.commit()

    doc = CurriculumDocument(id=uuid4(), title="Biology", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()

    chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="photosynthesis chlorophyll sunlight", text_hash=str(uuid4()))
    db_session.add(chunk)
    db_session.commit()

    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "addition regrouping"})
    assert res.status_code == 200
    data = res.json()
    assert data["semantic_search_used"] == False
    assert data["results"] == []

def test_grade_compatibility_real_retrieval(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-GRADE-{uuid4()}", name="Add", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    docs_def = [
        (1, 1, "A"),
        (2, 2, "B"),
        (3, 3, "C"),
        (None, None, "D"),
        (2, None, "E"),
        (None, 2, "F")
    ]
    
    for gmin, gmax, title in docs_def:
        doc = CurriculumDocument(id=uuid4(), title=title, source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{title}-{uuid4()}", status="ready", embedding_status="ready", grade_min=gmin, grade_max=gmax)
        db_session.add(doc)
        db_session.commit()
        chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="addition regrouping", text_hash=str(uuid4()))
        db_session.add(chunk)
        db_session.commit()
    
    # Request without explicit grade
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "addition regrouping"})
    assert res.status_code == 200
    titles = {r["source"]["title"] for r in res.json()["results"]}
    assert titles == {"B", "D", "E", "F"}
    assert "A" not in titles and "C" not in titles
    
    # Explicit grade override
    res2 = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "addition regrouping", "grade": 3})
    assert res2.status_code == 200
    titles2 = {r["source"]["title"] for r in res2.json()["results"]}
    assert titles2 == {"C", "D", "E"}
    assert "A" not in titles2 and "B" not in titles2 and "F" not in titles2
    meta2 = res2.json()["query"]
    assert meta2["requested_grade"] == 3
    assert meta2["effective_grade"] == 3
    
def test_lexical_transparency():
    from app.services.curriculum_retrieval import lexical_similarity
    score = lexical_similarity("Addition, regrouping!", "Regrouping in two-digit addition.")
    assert score == 1.0

def test_competency_mapping_scores(client, db_session):
    from app.services.curriculum_retrieval import competency_relevance
    from app.models.all_models import CurriculumChunkCompetency
    from uuid import uuid4
    cid = uuid4()
    assert competency_relevance([CurriculumChunkCompetency(competency_id=cid, mapping_type="manual")], cid) == 1.0
    assert competency_relevance([CurriculumChunkCompetency(competency_id=cid, mapping_type="metadata")], cid) == 0.9
    assert competency_relevance([CurriculumChunkCompetency(competency_id=cid, mapping_type="rule_based")], cid) == 0.9
    assert competency_relevance([CurriculumChunkCompetency(competency_id=cid, mapping_type="semantic", confidence=0.72)], cid) == 0.72
    assert competency_relevance([CurriculumChunkCompetency(competency_id=uuid4(), mapping_type="manual")], cid) == 0.0

def test_hybrid_score_reconstruction(client, db_session):
    from app.services.curriculum_retrieval import compute_hybrid_score
    from app.core.curriculum_config import COMPETENCY_MATCH_WEIGHT, LEXICAL_WEIGHT, SEMANTIC_WEIGHT
    
    comp_score = 1.0
    lex_score = 0.5
    sem_score = 0.8
    cw = COMPETENCY_MATCH_WEIGHT
    lw = LEXICAL_WEIGHT
    sw = SEMANTIC_WEIGHT
    tot = cw + lw + sw
    expected = round((comp_score * (cw/tot)) + (lex_score * (lw/tot)) + (sem_score * (sw/tot)), 6)
    
    assert compute_hybrid_score(comp_score, lex_score, sem_score) == expected
    
def test_lifecycle_and_archive(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-ARCH-{uuid4()}", name="A", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc_draft = CurriculumDocument(id=uuid4(), title="Draft", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="draft", embedding_status="ready")
    doc_proc = CurriculumDocument(id=uuid4(), title="Proc", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="processing", embedding_status="ready")
    doc_ready = CurriculumDocument(id=uuid4(), title="Ready", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="ready", embedding_status="ready")
    doc_fail = CurriculumDocument(id=uuid4(), title="Fail", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="failed", embedding_status="ready")
    doc_arch = CurriculumDocument(id=uuid4(), title="Archived", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="archived", embedding_status="ready")
    
    db_session.add_all([doc_draft, doc_proc, doc_ready, doc_fail, doc_arch])
    db_session.commit()
    
    for d in [doc_draft, doc_proc, doc_ready, doc_fail, doc_arch]:
        chunk = CurriculumChunk(id=uuid4(), document_id=d.id, chunk_index=0, text="A A A", text_hash=str(uuid4()))
        db_session.add(chunk)
    db_session.commit()

    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A A"})
    assert res.status_code == 200
    titles = {r["source"]["title"] for r in res.json()["results"]}
    assert titles == {"Ready"}
    
    arch_res = client.post(f"/api/v1/curriculum/documents/{doc_ready.id}/archive")
    assert arch_res.status_code == 200
    
    res2 = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A A"})
    titles2 = {r["source"]["title"] for r in res2.json()["results"]}
    assert "Ready" not in titles2
    
    # Assert DB unchanged
    d_check = db_session.query(CurriculumDocument).filter_by(id=doc_ready.id).first()
    assert d_check.status == "archived"
    c_check = db_session.query(CurriculumChunk).filter_by(document_id=doc_ready.id).first()
    assert c_check is not None

def test_language_behavior(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-LANG-{uuid4()}", name="A", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc_en = CurriculumDocument(id=uuid4(), title="En", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-EN-{uuid4()}", status="ready", embedding_status="ready")
    doc_hi = CurriculumDocument(id=uuid4(), title="Hi", source_type="reference", source_name="R", subject="math", language="hi", version="1", checksum=f"C-HI-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add_all([doc_en, doc_hi])
    db_session.commit()
    
    c_en = CurriculumChunk(id=uuid4(), document_id=doc_en.id, chunk_index=0, text="A A A", text_hash=str(uuid4()))
    c_hi = CurriculumChunk(id=uuid4(), document_id=doc_hi.id, chunk_index=0, text="A A A", text_hash=str(uuid4()))
    db_session.add_all([c_en, c_hi])
    db_session.commit()

    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A A", "language": "en"})
    assert res.status_code == 200
    titles = {r["source"]["title"] for r in res.json()["results"]}
    assert titles == {"En"}
    
    res2 = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A A"})
    titles2 = {r["source"]["title"] for r in res2.json()["results"]}
    assert titles2 == {"En", "Hi"}

def test_effective_query_metadata(client, db_session):
    from app.models.all_models import Competency
    from uuid import uuid4
    comp = Competency(code=f"NUM_ADD_2D-{uuid4()}", name="Addition", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id)})
    assert res.status_code == 200
    meta = res.json()["query"]
    assert meta["requested_query_text"] is None
    assert meta["effective_query_text"] == f"Addition {comp.code} math"
    assert meta["requested_grade"] is None
    assert meta["effective_grade"] == 2

def test_public_score_integrity():
    from app.services.curriculum_retrieval import compute_hybrid_score, lexical_similarity, semantic_relevance, competency_relevance
    h = compute_hybrid_score(1.0, 1.0, 1.0)
    assert 0 <= h <= 1.0
    h2 = compute_hybrid_score(0.0, 0.0, 0.0)
    assert 0 <= h2 <= 1.0
    h3 = compute_hybrid_score(1.0, 0.0, None)
    assert 0 <= h3 <= 1.0

def test_provenance_response(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-PROV-{uuid4()}", name="A", subject="math")
    db_session.add(comp)
    db_session.commit()
    doc = CurriculumDocument(id=uuid4(), title="Prov", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-PROV-{uuid4()}", status="ready", embedding_status="ready", metadata_json={"doc": 1})
    db_session.add(doc)
    db_session.commit()
    chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A A A", text_hash=str(uuid4()), metadata_json={"chunk": 1}, page_start=1, page_end=1)
    db_session.add(chunk)
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A A"})
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 1
    src = results[0]["source"]
    assert src["chunk_index"] == 0
    assert src["subject"] == "math"
    assert src["language"] == "en"
    assert src["document_metadata"] == {"doc": 1}
    assert src["chunk_metadata"] == {"chunk": 1}
    assert src["page_start"] == 1
    assert src["page_end"] == 1

def test_acceptance_addition_scenario_tightened(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
    from uuid import uuid4
    comp = Competency(code=f"NUM_ADD_2D_ACC_{uuid4()}", name="Two-digit addition", subject="math", grade=2)
    db_session.add(comp)
    db_session.commit()
    
    doc_a = CurriculumDocument(id=uuid4(), title="A", source_type="teacher_guide", source_name="R", subject="math", language="en", version="1", checksum=f"C-A-{uuid4()}", status="ready", embedding_status="ready", grade_min=2, grade_max=2)
    doc_b = CurriculumDocument(id=uuid4(), title="B", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-B-{uuid4()}", status="ready", embedding_status="ready", grade_min=2, grade_max=2)
    doc_c = CurriculumDocument(id=uuid4(), title="C", source_type="reference", source_name="R", subject="science", language="en", version="1", checksum=f"C-C-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add_all([doc_a, doc_b, doc_c])
    db_session.commit()
    
    chunk_a = CurriculumChunk(id=uuid4(), document_id=doc_a.id, chunk_index=0, text="Use place value when regrouping two-digit addition...", text_hash=str(uuid4()))
    chunk_b = CurriculumChunk(id=uuid4(), document_id=doc_b.id, chunk_index=0, text="generic unrelated geometry", text_hash=str(uuid4()))
    chunk_c = CurriculumChunk(id=uuid4(), document_id=doc_c.id, chunk_index=0, text="addition regrouping", text_hash=str(uuid4()))
    db_session.add_all([chunk_a, chunk_b, chunk_c])
    db_session.commit()
    
    db_session.add(CurriculumChunkCompetency(chunk_id=chunk_a.id, competency_id=comp.id, mapping_type="manual"))
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "addition regrouping"})
    assert res.status_code == 200
    results = res.json()["results"]
    returned_ids = {r["source"]["document_id"] for r in results}
    assert returned_ids == {str(doc_a.id)}

def test_stable_tie_breaking(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-TIE-{uuid4()}", name="A", subject="math")
    db_session.add(comp)
    db_session.commit()
    doc = CurriculumDocument(id=uuid4(), title="Prov", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-TIE-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()
    c1 = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=1, text="A A A", text_hash=str(uuid4()))
    c2 = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A A A", text_hash=str(uuid4()))
    db_session.add_all([c1, c2])
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A A"})
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 2
    assert results[0]["source"]["chunk_index"] == 0
    assert results[1]["source"]["chunk_index"] == 1
    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2

def test_all_mappings_preserved(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
    from uuid import uuid4
    c_target = Competency(code=f"T-TARG-{uuid4()}", name="Addition", subject="math")
    c_other1 = Competency(code=f"T-OTH1-{uuid4()}", name="Place Value", subject="math")
    c_other2 = Competency(code=f"T-OTH2-{uuid4()}", name="Number Sense", subject="math")
    db_session.add_all([c_target, c_other1, c_other2])
    db_session.commit()
    
    doc = CurriculumDocument(id=uuid4(), title="Doc", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-MAP-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()
    
    chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A A A", text_hash=str(uuid4()))
    db_session.add(chunk)
    db_session.commit()
    
    db_session.add_all([
        CurriculumChunkCompetency(chunk_id=chunk.id, competency_id=c_target.id, mapping_type="manual"),
        CurriculumChunkCompetency(chunk_id=chunk.id, competency_id=c_other1.id, mapping_type="metadata"),
        CurriculumChunkCompetency(chunk_id=chunk.id, competency_id=c_other2.id, mapping_type="rule_based")
    ])
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(c_target.id), "query_text": "A A A"})
    results = res.json()["results"]
    assert len(results) == 1
    assert results[0]["scores"]["competency"] == 1.0
    c_ids = {c["competency_id"] for c in results[0]["competencies"]}
    assert c_ids == {str(c_target.id), str(c_other1.id), str(c_other2.id)}

def test_ranking_mapped_vs_semantic(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
    from app.services.curriculum_retrieval import compute_hybrid_score
    from uuid import uuid4
    from app.api.routes.curriculum import get_embedding_provider
    
    comp = Competency(code=f"T-RANK1-{uuid4()}", name="Addition", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc = CurriculumDocument(id=uuid4(), title="Doc", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-R1-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()
    
    query_vec = unit_vector_768()
    chunk_a_vec = vector_with_cosine(0.60)
    chunk_b_vec = vector_with_cosine(0.70)
    
    ca = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A", text_hash=str(uuid4()), embedding=chunk_a_vec) 
    cb = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=1, text="A", text_hash=str(uuid4()), embedding=chunk_b_vec) 
    db_session.add_all([ca, cb])
    db_session.commit()
    
    db_session.add(CurriculumChunkCompetency(chunk_id=ca.id, competency_id=comp.id, mapping_type="manual"))
    db_session.commit()
    
    class P:
        def embed_texts(self, texts):
            return [query_vec for _ in texts]
    
    app.dependency_overrides[get_embedding_provider] = lambda: P()
    
    h_a = compute_hybrid_score(1.0, 1.0, 0.60)
    h_b = compute_hybrid_score(0.0, 1.0, 0.70)
    
    assert h_a > h_b
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A"})
    data = res.json()
    assert data["semantic_search_used"] is True
    assert all(r["scores"]["semantic"] is not None for r in data["results"])
    assert data["results"][0]["chunk_id"] == str(ca.id)
    assert data["results"][1]["chunk_id"] == str(cb.id)

def test_ranking_semantic_vs_mapped(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
    from app.services.curriculum_retrieval import compute_hybrid_score
    from uuid import uuid4
    from app.api.routes.curriculum import get_embedding_provider
    
    comp = Competency(code=f"T-RANK2-{uuid4()}", name="Addition", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc = CurriculumDocument(id=uuid4(), title="Doc", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-R2-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()
    
    query_vec = unit_vector_768()
    chunk_a_vec = vector_with_cosine(0.10)
    chunk_b_vec = unit_vector_768()
    
    ca = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="XYZ", text_hash=str(uuid4()), embedding=chunk_a_vec)
    cb = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=1, text="A", text_hash=str(uuid4()), embedding=chunk_b_vec) 
    db_session.add_all([ca, cb])
    db_session.commit()
    
    db_session.add(CurriculumChunkCompetency(chunk_id=ca.id, competency_id=comp.id, mapping_type="semantic", confidence=0.20))
    db_session.commit()
    
    class P:
        def embed_texts(self, texts):
            return [query_vec for _ in texts]
    app.dependency_overrides[get_embedding_provider] = lambda: P()
    
    h_a = compute_hybrid_score(0.20, 0.0, 0.10)
    h_b = compute_hybrid_score(0.0, 1.0, 1.0)
    assert h_b > h_a
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A"})
    data = res.json()
    assert data["semantic_search_used"] is True
    assert all(r["scores"]["semantic"] is not None for r in data["results"])
    assert data["results"][0]["chunk_id"] == str(cb.id)
    assert data["results"][1]["chunk_id"] == str(ca.id)

def test_actual_result_score_reconstruction_and_bounds(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from app.services.curriculum_retrieval import compute_hybrid_score
    from uuid import uuid4
    from app.api.routes.curriculum import get_embedding_provider
    import math
    
    comp = Competency(code=f"T-REC-{uuid4()}", name="Addition", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc = CurriculumDocument(id=uuid4(), title="Doc", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-REC-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add(doc)
    db_session.commit()
    
    query_vec = unit_vector_768()
    
    c_good = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=0, text="A A", text_hash=str(uuid4()), embedding=unit_vector_768())
    c_bad = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=1, text="A A", text_hash=str(uuid4()), embedding=[0.1]*767) # bad dimension!
    db_session.add_all([c_good, c_bad])
    db_session.commit()
    
    class P:
        def embed_texts(self, texts): return [query_vec for _ in texts]
    app.dependency_overrides[get_embedding_provider] = lambda: P()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A A"})
    assert res.status_code == 200
    assert res.json()["semantic_search_used"] is True
    results = res.json()["results"]
    assert len(results) == 2
    
    for r in results:
        scores = r["scores"]
        c, l, s, h = scores["competency"], scores["lexical"], scores["semantic"], scores["hybrid"]
        
        assert math.isfinite(c) and 0 <= c <= 1
        assert math.isfinite(l) and 0 <= l <= 1
        assert math.isfinite(h) and 0 <= h <= 1
        if s is not None:
            assert math.isfinite(s) and 0 <= s <= 1
            
        assert h == compute_hybrid_score(c, l, s)
        
    sem_values = {r["scores"]["semantic"] for r in results}
    assert None in sem_values
    assert 1.0 in sem_values

def test_semantic_null_vs_zero_tie():
    from types import SimpleNamespace
    from app.services.curriculum_retrieval import retrieval_sort_key

    ca = {
        "scores": {
            "hybrid": 0.5,
            "competency": 0.5,
            "semantic": 0.0,
            "lexical": 0.5,
        },
        "doc": SimpleNamespace(id="1"),
        "chunk": SimpleNamespace(chunk_index=0),
    }

    cb = {
        "scores": {
            "hybrid": 0.5,
            "competency": 0.5,
            "semantic": None,
            "lexical": 0.5,
        },
        "doc": SimpleNamespace(id="1"),
        "chunk": SimpleNamespace(chunk_index=1),
    }

    items = [cb, ca]
    items.sort(key=retrieval_sort_key)

    assert items[0] is ca
    assert items[1] is cb

def test_document_uuid_tie(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-TIEU-{uuid4()}", name="A", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    id1 = uuid4()
    id2 = uuid4()
    d_low = id1 if str(id1) < str(id2) else id2
    d_high = id2 if str(id1) < str(id2) else id1
    
    doc1 = CurriculumDocument(id=d_high, title="H", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="ready", embedding_status="ready")
    doc2 = CurriculumDocument(id=d_low, title="L", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-{uuid4()}", status="ready", embedding_status="ready")
    db_session.add_all([doc1, doc2])
    db_session.commit()
    
    c1 = CurriculumChunk(id=uuid4(), document_id=doc1.id, chunk_index=0, text="A", text_hash=str(uuid4()))
    c2 = CurriculumChunk(id=uuid4(), document_id=doc2.id, chunk_index=0, text="A", text_hash=str(uuid4()))
    db_session.add_all([c1, c2])
    db_session.commit()
    
    for _ in range(3):
        res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A"})
        results = res.json()["results"]
        assert results[0]["source"]["document_id"] == str(d_low)
        assert results[1]["source"]["document_id"] == str(d_high)

def test_provenance_completeness(client, db_session):
    from app.models.all_models import Competency, CurriculumDocument, CurriculumChunk
    from uuid import uuid4
    comp = Competency(code=f"T-PROV2-{uuid4()}", name="A", subject="math")
    db_session.add(comp)
    db_session.commit()
    
    doc = CurriculumDocument(id=uuid4(), title="Prov", source_type="reference", source_name="R", subject="math", language="en", version="1", checksum=f"C-PROV2-{uuid4()}", status="ready", embedding_status="ready", metadata_json={"doc": 1}, grade_min=1, grade_max=2)
    db_session.add(doc)
    db_session.commit()
    
    chunk = CurriculumChunk(id=uuid4(), document_id=doc.id, chunk_index=3, text="A", text_hash=str(uuid4()), metadata_json={"chunk": 1}, page_start=1, page_end=1, section_title="Sec")
    db_session.add(chunk)
    db_session.commit()
    
    res = client.post("/api/v1/curriculum/retrieve", json={"competency_id": str(comp.id), "query_text": "A"})
    results = res.json()["results"]
    r = results[0]
    s = r["source"]
    
    assert r["chunk_id"] == str(chunk.id)
    assert s["chunk_id"] == str(chunk.id)
    assert s["document_id"] == str(doc.id)
    assert s["chunk_index"] == 3
    assert s["title"] == "Prov"
    assert s["source_type"] == "reference"
    assert s["source_name"] == "R"
    assert s["version"] == "1"
    assert s["subject"] == "math"
    assert s["language"] == "en"
    assert s["grade_min"] == 1
    assert s["grade_max"] == 2
    assert s["page_start"] == 1
    assert s["page_end"] == 1
    assert s["section_title"] == "Sec"
    assert s["document_metadata"] == {"doc": 1}
    assert s["chunk_metadata"] == {"chunk": 1}

def test_source_type_validation(client):
    import pytest
    from pydantic import ValidationError
    from app.schemas.curriculum import CurriculumDocumentCreate

    for bad in ["T", "official", "trusted", "school"]:
        res = client.post(
            "/api/v1/curriculum/documents",
            json={
                "title": "A",
                "source_type": bad,
                "source_name": "R",
                "subject": "math",
                "language": "en",
                "version": "1.0",
                "content": "Valid content",
            },
        )
        assert res.status_code == 422

    valid_types = [
        "teacher_upload",
        "curriculum_framework",
        "textbook",
        "teacher_guide",
        "reference",
    ]

    for valid in valid_types:
        obj = CurriculumDocumentCreate(
            title="A",
            source_type=valid,
            source_name="R",
            subject="math",
            language="en",
            version="1.0",
            content="Valid content",
        )
        assert obj.source_type == valid

    with pytest.raises(ValidationError):
        CurriculumDocumentCreate(
            title="A",
            source_type="reference",
            source_name="R",
            subject="math",
        )
