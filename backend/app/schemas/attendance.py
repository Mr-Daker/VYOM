from pydantic import BaseModel, ConfigDict
from typing import List
from uuid import UUID
from app.models.enums import AttendanceStatus

class AttendanceRecordBase(BaseModel):
    student_id: UUID
    status: AttendanceStatus

class AttendanceRecordResponse(AttendanceRecordBase):
    id: UUID
    class_session_id: UUID
    model_config = ConfigDict(from_attributes=True)

class AttendanceBulkCreate(BaseModel):
    records: List[AttendanceRecordBase]
