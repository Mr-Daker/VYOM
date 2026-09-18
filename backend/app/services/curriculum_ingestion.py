from typing import List, Optional
import uuid
import math
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.all_models import CurriculumDocument, CurriculumChunk
from app.schemas.curriculum import CurriculumDocumentCreate
from app.services.text_processor import normalize_text, hash_text, chunk_text
from app.core.exceptions import (
    CurriculumContentEmptyError,
    CurriculumContentTooLargeError,
    CurriculumDocumentDuplicateError,
    CurriculumIngestionFailedError,
    EmbeddingDimensionMismatchError,
    CurriculumDocumentNotFoundError,
    CurriculumDocumentNotReadyError,
    CurriculumEmbeddingFailedError,
    AppException
)
from app.core.curriculum_config import MAX_CURRICULUM_TEXT_CHARS, CURRICULUM_EMBEDDING_DIMENSION, EMBEDDING_BATCH_SIZE
from app.services.embedding import EmbeddingProvider
from app.repositories.curriculum import CurriculumDocumentRepository, CurriculumChunkRepository

def validate_embedding_batch(texts: List[str], vectors: List[List[float]], expected_dimension: int):
    if not isinstance(vectors, (list, tuple)):
        raise CurriculumEmbeddingFailedError(details={"msg": "vectors must be a sequence"})
    if len(vectors) != len(texts):
        raise CurriculumEmbeddingFailedError(details={"msg": f"vector count {len(vectors)} does not match text count {len(texts)}"})
    for emb in vectors:
        if not isinstance(emb, (list, tuple)):
            raise CurriculumEmbeddingFailedError(details={"msg": "each vector must be a sequence"})
        if len(emb) != expected_dimension:
            raise EmbeddingDimensionMismatchError(details={"actual": len(emb), "expected": expected_dimension})
        for v in emb:
            if isinstance(v, bool):
                raise CurriculumEmbeddingFailedError(details={"msg": "vector elements must be numeric, not bool"})
            if not isinstance(v, (int, float)):
                raise CurriculumEmbeddingFailedError(details={"msg": "vector elements must be numeric"})
            if not math.isfinite(v):
                raise CurriculumEmbeddingFailedError(details={"msg": "vector elements must be finite"})

class CurriculumIngestionService:
    def __init__(self, db: Session, embedding_provider: Optional[EmbeddingProvider] = None):
        self.db = db
        self.embedding_provider = embedding_provider
        self.doc_repo = CurriculumDocumentRepository(db)
        self.chunk_repo = CurriculumChunkRepository(db)

    def ingest_document(self, request: CurriculumDocumentCreate) -> CurriculumDocument:
        try:
            if not request.content or not request.content.strip():
                raise CurriculumContentEmptyError()
                
            if len(request.content) > MAX_CURRICULUM_TEXT_CHARS:
                raise CurriculumContentTooLargeError()
                
            norm_content = normalize_text(request.content)
            checksum = hash_text(norm_content)
            
            existing = self.doc_repo.get_by_checksum(checksum)
            if existing:
                raise CurriculumDocumentDuplicateError(existing_id=str(existing.id))
                
            chunks_text = chunk_text(norm_content)
            if not chunks_text:
                raise CurriculumContentEmptyError()
                
            doc_id = uuid.uuid4()
            
            doc = CurriculumDocument(
                id=doc_id,
                title=request.title,
                source_type=request.source_type,
                source_name=request.source_name,
                subject=request.subject,
                grade_min=request.grade_min,
                grade_max=request.grade_max,
                language=request.language,
                version=request.version,
                checksum=checksum,
                status="ready",
                embedding_status="not_requested",
                metadata_json=request.metadata_json
            )
            
            embeddings = []
            if self.embedding_provider:
                try:
                    for i in range(0, len(chunks_text), EMBEDDING_BATCH_SIZE):
                        batch_texts = chunks_text[i:i+EMBEDDING_BATCH_SIZE]
                        batch_vectors = self.embedding_provider.embed_texts(batch_texts)
                        validate_embedding_batch(batch_texts, batch_vectors, CURRICULUM_EMBEDDING_DIMENSION)
                        embeddings.extend(batch_vectors)
                    doc.embedding_status = "ready"
                except AppException:
                    raise
                except Exception:
                    doc.embedding_status = "failed"
                    embeddings = []

            chunks = []
            for i, text in enumerate(chunks_text):
                emb = embeddings[i] if embeddings else None
                chunk = CurriculumChunk(
                    id=uuid.uuid4(),
                    document_id=doc_id,
                    chunk_index=i,
                    text=text,
                    text_hash=hash_text(text),
                    embedding=emb
                )
                chunks.append(chunk)
                
            # Persistence
            self.doc_repo.add(doc)
            self.doc_repo.flush()
            
            self.chunk_repo.add(chunks[0])
            self.chunk_repo.flush()
            
            for chunk in chunks[1:]:
                self.chunk_repo.add(chunk)
            self.chunk_repo.flush()
            
            self.db.commit()
            doc.chunk_count = len(chunks)
            return doc
            
        except AppException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise CurriculumIngestionFailedError()

    def retry_embeddings(self, doc_id: UUID) -> CurriculumDocument:
        try:
            doc = self.doc_repo.get_by_id(doc_id)
            if not doc:
                raise CurriculumDocumentNotFoundError(str(doc_id))
                
            if doc.status != "ready":
                raise CurriculumDocumentNotReadyError(str(doc_id))
                
            if not self.embedding_provider:
                raise CurriculumEmbeddingFailedError()
                
            chunks = self.db.query(CurriculumChunk).filter(CurriculumChunk.document_id == doc.id).order_by(CurriculumChunk.chunk_index).all()
            chunks_to_embed = [c for c in chunks if not c.embedding]
            
            if not chunks_to_embed:
                doc.embedding_status = "ready"
                self.db.commit()
                doc.chunk_count = len(chunks)
                return doc
                
            try:
                texts = [c.text for c in chunks_to_embed]
                embeddings = []
                for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                    batch_texts = texts[i:i+EMBEDDING_BATCH_SIZE]
                    batch_vectors = self.embedding_provider.embed_texts(batch_texts)
                    validate_embedding_batch(batch_texts, batch_vectors, CURRICULUM_EMBEDDING_DIMENSION)
                    embeddings.extend(batch_vectors)
                
                for i, emb in enumerate(embeddings):
                    chunks_to_embed[i].embedding = emb
                doc.embedding_status = "ready"
                self.db.commit()
            except AppException:
                raise
            except Exception:
                doc.embedding_status = "failed"
                self.db.commit()
                raise CurriculumEmbeddingFailedError()
                
            doc.chunk_count = len(chunks)
            return doc
        except AppException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise CurriculumIngestionFailedError()
