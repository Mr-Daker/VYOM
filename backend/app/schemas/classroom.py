from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID

class ClassroomBase(BaseModel):
    name: str
    teacher_id: UUID
    school_name: Optional[str] = None
    default_language: Optional[str] = None
    secondary_language: Optional[str] = None
    default_duration_minutes: Optional[int] = Field(None, gt=0)
    max_groups: Optional[int] = Field(None, gt=0)

class ClassroomCreate(ClassroomBase):
    pass

class ClassroomUpdate(BaseModel):
    name: Optional[str] = None
    school_name: Optional[str] = None
    default_language: Optional[str] = None
    secondary_language: Optional[str] = None
    default_duration_minutes: Optional[int] = Field(None, gt=0)
    max_groups: Optional[int] = Field(None, gt=0)

class ClassroomResponse(ClassroomBase):
    id: UUID
    model_config = ConfigDict(from_attributes=True)
