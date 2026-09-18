from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.enums import SessionStatus

class ClassSessionBase(BaseModel):
    subject: Optional[str] = None
    target_competency_id: Optional[UUID] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    available_materials: Optional[List[str]] = None
    status: SessionStatus = SessionStatus.DRAFT

class ClassSessionCreate(ClassSessionBase):
    pass

class ClassSessionUpdate(BaseModel):
    subject: Optional[str] = None
    target_competency_id: Optional[UUID] = None
    duration_minutes: Optional[int] = Field(None, gt=0)
    available_materials: Optional[List[str]] = None
    status: Optional[SessionStatus] = None

class ClassSessionResponse(ClassSessionBase):
    id: UUID
    classroom_id: UUID
    date: datetime
    model_config = ConfigDict(from_attributes=True)
