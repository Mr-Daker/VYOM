from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, and_
from uuid import UUID
from typing import List, Optional
from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency

class CurriculumDocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, doc: CurriculumDocument):
        self.db.add(doc)

    def flush(self):
        self.db.flush()

    def get_by_checksum(self, checksum: str) -> Optional[CurriculumDocument]:
        return self.db.query(CurriculumDocument).filter(CurriculumDocument.checksum == checksum).first()

    def get_by_id(self, doc_id: UUID) -> Optional[CurriculumDocument]:
        return self.db.query(CurriculumDocument).filter(CurriculumDocument.id == doc_id).first()
        
    def list_filtered(
        self,
        status: Optional[str] = None,
        subject: Optional[str] = None,
        grade: Optional[int] = None,
        language: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[int, List[CurriculumDocument]]:
        q = self.db.query(CurriculumDocument)
        if status:
            q = q.filter(CurriculumDocument.status == status)
        if subject:
            q = q.filter(CurriculumDocument.subject == subject)
        if language:
            q = q.filter(CurriculumDocument.language == language.lower())
        if grade is not None:
            q = q.filter(CurriculumDocument.grade_min <= grade, CurriculumDocument.grade_max >= grade)
            
        total = q.count()
        items = q.order_by(desc(CurriculumDocument.created_at), asc(CurriculumDocument.id)).offset(offset).limit(limit).all()
        return total, items

    def archive(self, doc_id: UUID) -> Optional[CurriculumDocument]:
        d = self.get_by_id(doc_id)
        if d:
            d.status = "archived"
        return d

class CurriculumChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, chunk: CurriculumChunk):
        self.db.add(chunk)

    def flush(self):
        self.db.flush()
        
    def add_all(self, chunks: List[CurriculumChunk]):
        self.db.add_all(chunks)
        
    def get_by_id(self, chunk_id: UUID) -> Optional[CurriculumChunk]:
        return self.db.query(CurriculumChunk).filter(CurriculumChunk.id == chunk_id).first()

    def list_by_document(self, document_id: UUID, limit: int = 50, offset: int = 0) -> tuple[int, List[CurriculumChunk]]:
        q = self.db.query(CurriculumChunk).filter(CurriculumChunk.document_id == document_id)
        total = q.count()
        items = q.order_by(asc(CurriculumChunk.chunk_index)).offset(offset).limit(limit).all()
        return total, items

    def count_by_document(self, document_id: UUID) -> int:
        return self.db.query(CurriculumChunk).filter(CurriculumChunk.document_id == document_id).count()

    def get_by_document(self, document_id: UUID) -> List[CurriculumChunk]:
        return self.db.query(CurriculumChunk).filter(CurriculumChunk.document_id == document_id).order_by(asc(CurriculumChunk.chunk_index)).all()

class CurriculumMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, mapping: CurriculumChunkCompetency):
        self.db.add(mapping)

    def flush(self):
        self.db.flush()
        
    def get_for_chunk(self, chunk_id: UUID) -> List[CurriculumChunkCompetency]:
        return self.db.query(CurriculumChunkCompetency).filter(CurriculumChunkCompetency.chunk_id == chunk_id).all()
        
    def get_existing_pairs(self, chunk_id: UUID, competency_ids: List[UUID]) -> List[CurriculumChunkCompetency]:
        return self.db.query(CurriculumChunkCompetency).filter(
            CurriculumChunkCompetency.chunk_id == chunk_id,
            CurriculumChunkCompetency.competency_id.in_(competency_ids)
        ).all()
        
    def list_for_chunks(self, chunk_ids: List[UUID]) -> List[CurriculumChunkCompetency]:
        return self.db.query(CurriculumChunkCompetency).filter(CurriculumChunkCompetency.chunk_id.in_(chunk_ids)).all()

