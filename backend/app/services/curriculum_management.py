from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session
from app.repositories.curriculum import CurriculumDocumentRepository, CurriculumChunkRepository, CurriculumMappingRepository
from app.models.all_models import CurriculumDocument, CurriculumChunk, CurriculumChunkCompetency, Competency
from app.schemas.curriculum import MappingCreate, CurriculumDocumentResponse
from app.core.exceptions import (
    CurriculumDocumentNotFoundError,
    CurriculumChunkNotFoundError,
    CurriculumMappingInvalidError,
    AppException
)

class CurriculumManagementService:
    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = CurriculumDocumentRepository(db)
        self.chunk_repo = CurriculumChunkRepository(db)
        self.map_repo = CurriculumMappingRepository(db)

    def list_documents(self, status: Optional[str] = None, subject: Optional[str] = None, grade: Optional[int] = None, language: Optional[str] = None, limit: int = 50, offset: int = 0):
        total, items = self.doc_repo.list_filtered(status, subject, grade, language, limit, offset)
        results = []
        for d in items:
            resp = CurriculumDocumentResponse.from_orm(d)
            resp.chunk_count = self.chunk_repo.count_by_document(d.id)
            results.append(resp)
        return total, results

    def get_document(self, document_id: UUID) -> CurriculumDocumentResponse:
        d = self.doc_repo.get_by_id(document_id)
        if not d:
            raise CurriculumDocumentNotFoundError(str(document_id))
        resp = CurriculumDocumentResponse.from_orm(d)
        resp.chunk_count = self.chunk_repo.count_by_document(d.id)
        return resp

    def archive_document(self, document_id: UUID) -> CurriculumDocumentResponse:
        try:
            d = self.doc_repo.archive(document_id)
            if not d:
                raise CurriculumDocumentNotFoundError(str(document_id))
            self.db.commit()
            
            resp = CurriculumDocumentResponse.from_orm(d)
            resp.chunk_count = self.chunk_repo.count_by_document(d.id)
            return resp
        except Exception:
            self.db.rollback()
            raise

    def list_chunks(self, document_id: UUID, limit: int = 50, offset: int = 0):
        d = self.doc_repo.get_by_id(document_id)
        if not d:
            raise CurriculumDocumentNotFoundError(str(document_id))
        return self.chunk_repo.list_by_document(document_id, limit, offset)

    def map_chunk_competencies(self, chunk_id: UUID, req: MappingCreate):
        try:
            c = self.chunk_repo.get_by_id(chunk_id)
            if not c:
                raise CurriculumChunkNotFoundError()
                
            comps = self.db.query(Competency).filter(Competency.id.in_(req.competency_ids)).all()
            if len(comps) != len(req.competency_ids):
                raise CurriculumMappingInvalidError()
                
            existing = self.map_repo.get_existing_pairs(chunk_id, req.competency_ids)
            existing_ids = {m.competency_id for m in existing}
            
            for cid in req.competency_ids:
                if cid not in existing_ids:
                    m = CurriculumChunkCompetency(
                        chunk_id=chunk_id,
                        competency_id=cid,
                        mapping_type=req.mapping_type,
                        confidence=req.confidence
                    )
                    self.map_repo.add(m)
            self.map_repo.flush()
            self.db.commit()
        except AppException:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

