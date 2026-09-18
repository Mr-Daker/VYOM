from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from uuid import UUID

class StudentBase(BaseModel):
    name: str
    grade: int = Field(..., ge=1, le=3)
    preferred_language: Optional[str] = None
    active: bool = True

class StudentCreate(StudentBase):
    pass

class StudentUpdate(BaseModel):
    name: Optional[str] = None
    grade: Optional[int] = Field(None, ge=1, le=3)
    preferred_language: Optional[str] = None
    active: Optional[bool] = None

class StudentResponse(StudentBase):
    id: UUID
    classroom_id: UUID
    model_config = ConfigDict(from_attributes=True)

class StudentBulkCreate(BaseModel):
    students: List[StudentCreate]
