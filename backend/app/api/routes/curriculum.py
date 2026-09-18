from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional, List
from app.db.session import get_db
from app.schemas.curriculum import (
    CurriculumDocumentCreate, CurriculumDocumentResponse,
    PaginatedDocuments, PaginatedChunks, MappingCreate,
    CurriculumQuery, RetrievalResponse
)
from app.services.curriculum_ingestion import CurriculumIngestionService
from app.services.curriculum_retrieval import CurriculumRetrievalService
from app.services.curriculum_management import CurriculumManagementService
from app.services.embedding import EmbeddingProvider

router = APIRouter(prefix="/api/v1/curriculum", tags=["curriculum"])

def get_embedding_provider() -> Optional[EmbeddingProvider]:
    return None

def get_ingestion_service(
    db: Session = Depends(get_db),
    provider: Optional[EmbeddingProvider] = Depends(get_embedding_provider)
):
    return CurriculumIngestionService(db, provider)

def get_retrieval_service(
    db: Session = Depends(get_db),
    provider: Optional[EmbeddingProvider] = Depends(get_embedding_provider)
):
    return CurriculumRetrievalService(db, provider)

def get_management_service(db: Session = Depends(get_db)):
    return CurriculumManagementService(db)

@router.post("/documents", response_model=CurriculumDocumentResponse, status_code=201)
def ingest_document(request: CurriculumDocumentCreate, service: CurriculumIngestionService = Depends(get_ingestion_service)):
    return service.ingest_document(request)

@router.get("/documents", response_model=PaginatedDocuments)
def list_documents(
    status: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[int] = None,
    language: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: CurriculumManagementService = Depends(get_management_service)
):
    total, items = service.list_documents(status, subject, grade, language, limit, offset)
    return PaginatedDocuments(total=total, limit=limit, offset=offset, items=items)

@router.get("/documents/{document_id}", response_model=CurriculumDocumentResponse)
def get_document(document_id: UUID, service: CurriculumManagementService = Depends(get_management_service)):
    return service.get_document(document_id)

@router.post("/documents/{document_id}/archive", response_model=CurriculumDocumentResponse)
def archive_document(document_id: UUID, service: CurriculumManagementService = Depends(get_management_service)):
    return service.archive_document(document_id)

@router.post("/documents/{document_id}/embed", response_model=CurriculumDocumentResponse)
def retry_embeddings(document_id: UUID, service: CurriculumIngestionService = Depends(get_ingestion_service)):
    return service.retry_embeddings(document_id)

@router.get("/documents/{document_id}/chunks", response_model=PaginatedChunks)
def list_chunks(
    document_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: CurriculumManagementService = Depends(get_management_service)
):
    total, items = service.list_chunks(document_id, limit, offset)
    return PaginatedChunks(total=total, limit=limit, offset=offset, items=items)

@router.post("/chunks/{chunk_id}/competencies")
def map_chunk_competencies(chunk_id: UUID, req: MappingCreate, service: CurriculumManagementService = Depends(get_management_service)):
    service.map_chunk_competencies(chunk_id, req)
    return {"status": "ok"}

@router.post("/retrieve", response_model=RetrievalResponse)
def retrieve_curriculum(req: CurriculumQuery, service: CurriculumRetrievalService = Depends(get_retrieval_service)):
    return service.retrieve(req)
