from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from uuid import UUID
from datetime import datetime

class FactorBreakdown(BaseModel):
    raw: float
    weight: int
    contribution: float

class PriorityFactors(BaseModel):
    instructional_need: FactorBreakdown
    evidence_severity: FactorBreakdown
    uncertainty: FactorBreakdown
    missed_instruction: FactorBreakdown
    group_complexity: FactorBreakdown
    reach: FactorBreakdown

class GroupPriorityResponse(BaseModel):
    group_id: UUID
    group_name: str
    group_type: str
    
    priority_rank: int
    priority_score: float
    priority_tier: str
    
    teacher_rank: Optional[int] = None
    teacher_override_reason: Optional[str] = None
    effective_rank: int
    
    student_count: int
    current_student_count: Optional[int] = None
    
    factor_breakdown: PriorityFactors
    top_reason: str
    reasons: List[str]

class PrioritySummary(BaseModel):
    groups_ranked: int
    urgent: int
    high: int
    moderate: int
    low: int

class SessionPriorityResponse(BaseModel):
    session_id: UUID
    generated: bool
    generated_at: Optional[datetime] = None
    stale: bool
    
    weights: Dict[str, int]
    priorities: List[GroupPriorityResponse]
    summary: Optional[PrioritySummary] = None

class GeneratePriorityRequest(BaseModel):
    replace_existing: bool = False
    force_replace_teacher_priority: bool = False
    
class ReorderPriorityRequest(BaseModel):
    ordered_group_ids: List[UUID]
    reason: Optional[str] = None
