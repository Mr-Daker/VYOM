from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID

class CompetencyBase(BaseModel):
    code: str
    subject: str
    grade: Optional[int] = Field(None, ge=1, le=3)
    name: str
    description: Optional[str] = None

class CompetencyCreate(CompetencyBase):
    pass

class CompetencyResponse(CompetencyBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)

class CompetencyPrerequisiteCreate(BaseModel):
    prerequisite_competency_id: UUID

class CompetencyPrerequisiteResponse(BaseModel):
    id: UUID
    competency_id: UUID
    prerequisite_competency_id: UUID
    model_config = ConfigDict(from_attributes=True)
