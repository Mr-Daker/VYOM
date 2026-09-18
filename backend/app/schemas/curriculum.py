from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from datetime import datetime
from app.core.curriculum_config import MAX_RETRIEVAL_TOP_K

from typing import Literal

class CurriculumDocumentCreate(BaseModel):
    title: str
    source_type: Literal["teacher_upload", "curriculum_framework", "textbook", "teacher_guide", "reference"]
    source_name: str
    subject: str
    grade_min: Optional[int] = None
    grade_max: Optional[int] = None
    language: str
    version: str
    content: str
    metadata_json: Optional[Dict[str, Any]] = None

    @field_validator("title", "source_type", "source_name", "subject", "version", "language", mode="before")
    @classmethod
    def must_be_nonblank(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Field cannot be blank")
        return v
        
    @field_validator("language", mode="after")
    @classmethod
    def language_lowercase(cls, v: str) -> str:
        return v.lower()
        
    @model_validator(mode="after")
    def validate_grades(self):
        g_min = self.grade_min
        g_max = self.grade_max
        if g_min is not None and g_min < 1:
            raise ValueError("grade_min must be >= 1")
        if g_max is not None and g_max < 1:
            raise ValueError("grade_max must be >= 1")
        if g_min is not None and g_max is not None:
            if g_min > g_max:
                raise ValueError("grade_min cannot be greater than grade_max")
        return self

class CurriculumDocumentResponse(BaseModel):
    id: UUID
    title: str
    source_type: Literal["teacher_upload", "curriculum_framework", "textbook", "teacher_guide", "reference"]
    source_name: str
    subject: str
    grade_min: Optional[int]
    grade_max: Optional[int]
    language: str
    version: str
    checksum: str
    status: str
    embedding_status: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    chunk_count: int = 0
    
    class Config:
        from_attributes = True

class PaginatedDocuments(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[CurriculumDocumentResponse]

class CurriculumChunkResponse(BaseModel):
    id: UUID
    document_id: UUID
    chunk_index: int
    text: str
    text_hash: str
    page_start: Optional[int]
    page_end: Optional[int]
    section_title: Optional[str]
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class PaginatedChunks(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[CurriculumChunkResponse]

class MappingCreate(BaseModel):
    competency_ids: List[UUID] = Field(min_length=1)
    mapping_type: Literal["manual", "metadata", "rule_based", "semantic"]
    confidence: Optional[float] = None
    
    @model_validator(mode="after")
    def validate_confidence(self):
        if self.mapping_type == "semantic":
            if self.confidence is None or not (0.0 <= self.confidence <= 1.0):
                raise ValueError("semantic mapping requires confidence between 0.0 and 1.0")
        else:
            if self.confidence is not None:
                raise ValueError("confidence must be omitted/null for non-semantic mappings")
        return self

class CurriculumQuery(BaseModel):
    competency_id: UUID
    query_text: Optional[str] = None
    grade: Optional[int] = None
    language: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=MAX_RETRIEVAL_TOP_K)
    
    @field_validator("query_text", "language", mode="before")
    @classmethod
    def must_be_nonblank(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Field cannot be blank")
        return v
        
    @field_validator("language", mode="after")
    @classmethod
    def language_lowercase(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return v.lower()
        return v
        
    @field_validator("grade", mode="after")
    @classmethod
    def validate_grade(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("grade must be >= 1")
        return v

class RetrievalQueryMeta(BaseModel):
    competency_id: UUID
    requested_query_text: Optional[str] = None
    effective_query_text: str
    requested_grade: Optional[int] = None
    effective_grade: Optional[int] = None
    language: Optional[str] = None

class RetrievalSource(BaseModel):
    document_id: UUID
    chunk_id: UUID
    chunk_index: int
    title: str
    source_type: Literal["teacher_upload", "curriculum_framework", "textbook", "teacher_guide", "reference"]
    source_name: str
    version: str
    subject: str
    language: str
    grade_min: Optional[int] = None
    grade_max: Optional[int] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_title: Optional[str] = None
    document_metadata: Optional[Dict[str, Any]] = None
    chunk_metadata: Optional[Dict[str, Any]] = None

class MappedCompetency(BaseModel):
    competency_id: UUID
    mapping_type: str
    confidence: Optional[float]

class RetrievalScores(BaseModel):
    competency: float
    lexical: float
    semantic: Optional[float]
    hybrid: float

class RetrievalResultItem(BaseModel):
    rank: int
    chunk_id: UUID
    text: str
    source: RetrievalSource
    competencies: List[MappedCompetency]
    scores: RetrievalScores

class RetrievalResponse(BaseModel):
    query: RetrievalQueryMeta
    semantic_search_used: bool
    results: List[RetrievalResultItem]
