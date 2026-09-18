from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import RotationSlotType

class RotationConfigResponse(BaseModel):
    opening_minutes: int
    closing_minutes: int
    transition_minutes: int
    minimum_group_attention_minutes: int

class RotationSummary(BaseModel):
    group_count: int
    teacher_attention_budget_minutes: int
    transition_total_minutes: int
    allocated_teacher_minutes: int

class GroupRotationAllocation(BaseModel):
    group_id: UUID
    group_name: str
    group_type: str
    
    priority_score: float
    
    algorithm_priority_rank: int
    teacher_rank: Optional[int]
    effective_rank: int
    
    student_count: int
    
    base_minutes: int
    weighted_extra_minutes: int
    allocated_teacher_minutes: int
    
    independent_minutes: int
    reason: str

class RotationSlotResponse(BaseModel):
    sequence_index: int
    slot_type: RotationSlotType
    start_minute: int
    end_minute: int
    duration_minutes: int
    group_id: Optional[UUID] = None
    reason: Optional[str] = None

class RotationPlanResponse(BaseModel):
    session_id: UUID
    generated: bool
    session_duration_minutes: Optional[int] = None
    configuration: Optional[RotationConfigResponse] = None
    summary: Optional[RotationSummary] = None
    group_allocations: Optional[List[GroupRotationAllocation]] = None
    slots: List[RotationSlotResponse] = Field(default_factory=list)
