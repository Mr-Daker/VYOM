from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Any, Dict
from uuid import UUID

from app.core.activity_config import (
    ACTIVITY_MAX_MATERIALS,
    ACTIVITY_MATERIAL_MAX_CHARS,
    ACTIVITY_TITLE_MAX_CHARS,
    ACTIVITY_OBJECTIVE_MAX_CHARS,
    ACTIVITY_STEP_MAX_CHARS,
    ACTIVITY_MAX_STEPS,
    ACTIVITY_MAX_CITATIONS
)

class ActivityGenerationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    available_materials: List[str] = Field(default_factory=lambda: ["notebook", "pencil", "board"])
    language: str = Field(default="en")
    
    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Any) -> str:
        if isinstance(v, str):
            v = v.strip().casefold()
            if not v:
                raise ValueError("Language cannot be blank")
            if len(v) > 20:
                raise ValueError("Language too long")
            return v
        raise ValueError("Invalid language")
    
    @field_validator("available_materials", mode="after")
    @classmethod
    def validate_materials(cls, v: List[str]) -> List[str]:
        if len(v) > ACTIVITY_MAX_MATERIALS:
            raise ValueError(f"Too many materials (max {ACTIVITY_MAX_MATERIALS})")
        res = []
        for item in v:
            val = item.strip()
            if not val:
                raise ValueError("Material cannot be blank")
            if len(val) > ACTIVITY_MATERIAL_MAX_CHARS:
                raise ValueError(f"Material name too long (max {ACTIVITY_MATERIAL_MAX_CHARS} chars)")
            res.append(val)
        return res

class GeneratedActivityContent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(..., min_length=1, max_length=ACTIVITY_TITLE_MAX_CHARS)
    objective: str = Field(..., min_length=1, max_length=ACTIVITY_OBJECTIVE_MAX_CHARS)
    duration_minutes: int = Field(gt=0)
    materials: List[str] = Field(max_length=ACTIVITY_MAX_MATERIALS)
    teacher_actions: List[str] = Field(..., min_length=1, max_length=ACTIVITY_MAX_STEPS)
    student_actions: List[str] = Field(..., min_length=1, max_length=ACTIVITY_MAX_STEPS)
    checks_for_understanding: List[str] = Field(max_length=ACTIVITY_MAX_STEPS)
    success_criteria: List[str] = Field(..., min_length=1, max_length=ACTIVITY_MAX_STEPS)
    adaptations: List[str] = Field(max_length=ACTIVITY_MAX_STEPS)
    source_chunk_ids: List[UUID] = Field(..., min_length=1, max_length=ACTIVITY_MAX_CITATIONS)

    @field_validator("title", "objective", mode="before")
    @classmethod
    def validate_strings(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("String cannot be empty")
        return v

    @field_validator("materials", mode="after")
    @classmethod
    def validate_generated_materials(cls, v: List[str]) -> List[str]:
        res = []
        seen = set()
        for item in v:
            val = item.strip()
            if not val:
                raise ValueError("Blank material generated")
            if len(val) > ACTIVITY_MATERIAL_MAX_CHARS:
                raise ValueError("Material too long")
            if val.casefold() in seen:
                raise ValueError("Duplicate generated materials are not allowed")
            seen.add(val.casefold())
            res.append(val)
        return res
        
    @field_validator("teacher_actions", "student_actions", "success_criteria", mode="after")
    @classmethod
    def validate_required_lists(cls, v: List[str]) -> List[str]:
        res = []
        for item in v:
            val = item.strip()
            if not val:
                raise ValueError("Blank item generated")
            if len(val) > ACTIVITY_STEP_MAX_CHARS:
                raise ValueError(f"Item exceeds {ACTIVITY_STEP_MAX_CHARS} chars")
            res.append(val)
        if len(res) < 1:
            raise ValueError("List cannot be empty")
        return res

    @field_validator("checks_for_understanding", "adaptations", mode="after")
    @classmethod
    def validate_optional_lists(cls, v: List[str]) -> List[str]:
        res = []
        for item in v:
            val = item.strip()
            if not val:
                raise ValueError("Blank item generated")
            if len(val) > ACTIVITY_STEP_MAX_CHARS:
                raise ValueError(f"Item exceeds {ACTIVITY_STEP_MAX_CHARS} chars")
            res.append(val)
        return res
        
    @field_validator("source_chunk_ids", mode="after")
    @classmethod
    def check_duplicate_citations(cls, v: List[UUID]) -> List[UUID]:
        if len(set(v)) != len(v):
            raise ValueError("Duplicate source chunk IDs are not allowed")
        return v

class ActivitySourceCitationResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    source_name: str
    source_type: str
    version: str
    section_title: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

class GroupActivityResponse(BaseModel):
    group_activity_id: UUID
    group_id: UUID
    group_name: str
    group_type: str
    focus_competency_id: UUID
    duration_minutes: int
    teacher_attention_minutes: int
    independent_minutes: int
    title: str
    objective: str
    materials: List[str]
    teacher_actions: List[str]
    student_actions: List[str]
    checks_for_understanding: List[str]
    success_criteria: List[str]
    adaptations: List[str]
    citations: List[ActivitySourceCitationResponse]
    approval_status: str

class ActivityPlanResponse(BaseModel):
    activity_plan_id: UUID
    session_id: UUID
    status: str
    prompt_version: str
    provider_name: str
    model_name: str
    activities: List[GroupActivityResponse]
