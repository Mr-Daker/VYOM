from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from app.models.enums import MasteryState

class StudentMasteryCreate(BaseModel):
    competency_id: UUID
    score: float = Field(..., ge=0.0, le=1.0)
    state: MasteryState
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

class StudentMasteryResponse(BaseModel):
    id: UUID
    student_id: UUID
    competency_id: UUID
    score: float
    state: MasteryState
    confidence: Optional[float]
    model_config = ConfigDict(from_attributes=True)
