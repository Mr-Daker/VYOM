import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency
from app.schemas.curriculum import (
    CurriculumQuery, RetrievalResponse, RetrievalResultItem,
    RetrievalQueryMeta, RetrievalSource, MappedCompetency, RetrievalScores
)
from app.core.exceptions import (
    CompetencyNotFoundError, CurriculumDocumentNotReadyError,
    RetrievalFailedError, AppException
)
from app.core.curriculum_config import (
    CURRICULUM_RETRIEVAL_TOP_K, MAX_RETRIEVAL_TOP_K,
    COMPETENCY_MATCH_WEIGHT, LEXICAL_WEIGHT, SEMANTIC_WEIGHT,
    CURRICULUM_EMBEDDING_DIMENSION
)
from app.services.embedding import EmbeddingProvider
from app.services.text_processor import normalize_text
from app.services.curriculum_ingestion import validate_embedding_batch
import math
import re
from collections import defaultdict

TOKEN_RE = re.compile(r"\b\w+\b", re.UNICODE)

def lexical_tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_RE.findall(normalize_text(text))}

def lexical_similarity(query: str, text: str) -> float:
    q_tokens = lexical_tokens(query)
    if not q_tokens:
        return 0.0
    t_tokens = lexical_tokens(text)
    if not t_tokens:
        return 0.0
    overlap = q_tokens.intersection(t_tokens)
    return round(len(overlap) / len(q_tokens), 6)

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if len(v1) != len(v2):
        raise ValueError(f"Vector dimensions do not match: {len(v1)} vs {len(v2)}")
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)

def semantic_relevance(query_vector: List[float], chunk_vector: List[float]) -> float:
    return round(max(0.0, min(1.0, cosine_similarity(query_vector, chunk_vector))), 6)

def competency_relevance(mappings: List[CurriculumChunkCompetency], target_competency_id: uuid.UUID) -> float:
    comp_score = 0.0
    for m in mappings:
        if m.competency_id == target_competency_id:
            if m.mapping_type == "manual":
                comp_score = max(comp_score, 1.0)
            elif m.mapping_type in ("metadata", "rule_based"):
                comp_score = max(comp_score, 0.9)
            elif m.mapping_type == "semantic" and m.confidence is not None:
                comp_score = max(comp_score, m.confidence)
    return comp_score

def compute_hybrid_score(competency_score: float, lexical_score: float, semantic_score: Optional[float]) -> float:
    cw = COMPETENCY_MATCH_WEIGHT
    lw = LEXICAL_WEIGHT
    sw = SEMANTIC_WEIGHT if semantic_score is not None else 0.0
    
    total_w = cw + lw + sw
    if total_w == 0:
        total_w = 1.0
    cw = cw / total_w
    lw = lw / total_w
    sw = sw / total_w
    
    s_score = semantic_score if semantic_score is not None else 0.0
    
    return round((competency_score * cw) + (lexical_score * lw) + (s_score * sw), 6)


def retrieval_sort_key(candidate):
    sem = candidate["scores"]["semantic"]
    return (
        -candidate["scores"]["hybrid"],
        -candidate["scores"]["competency"],
        sem is None,
        -sem if sem is not None else 0.0,
        -candidate["scores"]["lexical"],
        str(candidate["doc"].id),
        candidate["chunk"].chunk_index,
    )

class CurriculumRetrievalService:
    def __init__(self, db: Session, embedding_provider: Optional[EmbeddingProvider] = None):
        self.db = db
        self.embedding_provider = embedding_provider

    def retrieve(self, query: CurriculumQuery) -> RetrievalResponse:
        from app.models.all_models import Competency
        comp = self.db.query(Competency).filter(Competency.id == query.competency_id).first()
        if not comp:
            raise CompetencyNotFoundError(str(query.competency_id))
            
        top_k = query.top_k
            
        effective_query_text = query.query_text
        if not effective_query_text:
            parts = [comp.name, comp.code, comp.subject]
            effective_query_text = " ".join(p.strip() for p in parts if p and p.strip())
            
        q_emb = None
        if self.embedding_provider:
            try:
                vectors = self.embedding_provider.embed_texts([effective_query_text])
                validate_embedding_batch([effective_query_text], vectors, CURRICULUM_EMBEDDING_DIMENSION)
                q_emb = vectors[0]
            except Exception:
                q_emb = None
        
        effective_grade = query.grade if query.grade is not None else comp.grade
        
        doc_query = self.db.query(CurriculumDocument).filter(CurriculumDocument.status == "ready")
        doc_query = doc_query.filter(CurriculumDocument.subject == comp.subject)
        
        if effective_grade is not None:
            doc_query = doc_query.filter(
                and_(
                    or_(CurriculumDocument.grade_min == None, CurriculumDocument.grade_min <= effective_grade),
                    or_(CurriculumDocument.grade_max == None, CurriculumDocument.grade_max >= effective_grade)
                )
            )
        if query.language:
            doc_query = doc_query.filter(CurriculumDocument.language == query.language.lower())
            
        docs = doc_query.all()
        doc_map = {d.id: d for d in docs}
        
        if not docs:
            return RetrievalResponse(
                query=RetrievalQueryMeta(
                    competency_id=query.competency_id, 
                    requested_query_text=query.query_text, 
                    effective_query_text=effective_query_text,
                    requested_grade=query.grade,
                    effective_grade=effective_grade,
                    language=query.language
                ),
                semantic_search_used=False,
                results=[]
            )
            
        chunks = self.db.query(CurriculumChunk).filter(CurriculumChunk.document_id.in_(list(doc_map.keys()))).all()
        chunk_map = {c.id: c for c in chunks}
        
        mappings = self.db.query(CurriculumChunkCompetency).filter(
            CurriculumChunkCompetency.chunk_id.in_(list(chunk_map.keys()))
        ).all()
        
        map_by_chunk = defaultdict(list)
        for m in mappings:
            map_by_chunk[m.chunk_id].append(m)
            
        candidates = []
        for c in chunks:
            ms = map_by_chunk[c.id]
            comp_score = competency_relevance(ms, query.competency_id)
            lex_score = lexical_similarity(effective_query_text, c.text)
            
            sem_score = None
            if q_emb is not None and c.embedding is not None:
                try:
                    validate_embedding_batch([c.text], [c.embedding], CURRICULUM_EMBEDDING_DIMENSION)
                    sem_score = semantic_relevance(q_emb, c.embedding)
                except Exception:
                    sem_score = None
                    
            is_relevant = (
                comp_score > 0 or 
                lex_score > 0 or 
                (sem_score is not None and sem_score > 0)
            )
            if not is_relevant:
                continue
                
            hybrid = compute_hybrid_score(comp_score, lex_score, sem_score)
            
            candidates.append({
                "chunk": c,
                "doc": doc_map[c.document_id],
                "mappings": ms,
                "scores": {
                    "competency": comp_score,
                    "lexical": lex_score,
                    "semantic": sem_score,
                    "hybrid": hybrid
                }
            })
            
        candidates.sort(key=retrieval_sort_key)
        
        returned = candidates[:top_k]
        semantic_search_used = any(r["scores"]["semantic"] is not None for r in returned)
        
        results = []
        for i, cand in enumerate(returned):
            mc = [MappedCompetency(competency_id=m.competency_id, mapping_type=m.mapping_type, confidence=m.confidence) for m in cand["mappings"]]
            src = RetrievalSource(
                document_id=cand["doc"].id,
                chunk_id=cand["chunk"].id,
                chunk_index=cand["chunk"].chunk_index,
                title=cand["doc"].title,
                source_type=cand["doc"].source_type,
                source_name=cand["doc"].source_name,
                version=cand["doc"].version,
                subject=cand["doc"].subject,
                language=cand["doc"].language,
                grade_min=cand["doc"].grade_min,
                grade_max=cand["doc"].grade_max,
                page_start=cand["chunk"].page_start,
                page_end=cand["chunk"].page_end,
                section_title=cand["chunk"].section_title,
                document_metadata=cand["doc"].metadata_json,
                chunk_metadata=cand["chunk"].metadata_json
            )
            sc = RetrievalScores(**cand["scores"])
            res = RetrievalResultItem(
                rank=i+1,
                chunk_id=cand["chunk"].id,
                text=cand["chunk"].text,
                source=src,
                competencies=mc,
                scores=sc
            )
            results.append(res)
            
        return RetrievalResponse(
            query=RetrievalQueryMeta(
                competency_id=query.competency_id, 
                requested_query_text=query.query_text, 
                effective_query_text=effective_query_text,
                requested_grade=query.grade,
                effective_grade=effective_grade,
                language=query.language
            ),
            semantic_search_used=semantic_search_used,
            results=results
        )
