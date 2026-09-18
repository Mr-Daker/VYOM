from pydantic import BaseModel
from typing import List, Optional, Dict
from uuid import UUID

class CompetencyRef(BaseModel):
    id: UUID
    code: str
    name: str

class GroupMemberResponse(BaseModel):
    student_id: UUID
    name: str
    grade: int
    preferred_language: Optional[str] = None
    focus_competency_id: Optional[UUID] = None
    assignment_reason: str
    original_group_type: Optional[str] = None
    original_check_mode: Optional[str] = None
    teacher_override_reason: Optional[str] = None
    target_mastery_score: Optional[float] = None
    target_mastery_state: Optional[str] = None
    target_mastery_source: Optional[str] = None
    target_mastery_stale: Optional[bool] = None

class LearningGroupResponse(BaseModel):
    id: UUID
    name: str
    group_type: str
    check_mode: Optional[str] = None
    focus_competency: Optional[CompetencyRef] = None
    student_count: int
    mixed_needs: bool
    grade_distribution: Dict[str, int]
    language_distribution: Dict[str, int]
    reason: str
    students: List[GroupMemberResponse]

class ExcludedStudentResponse(BaseModel):
    student_id: UUID
    name: str
    reason: str

class GroupingSummary(BaseModel):
    active_students: int
    eligible_students: int
    absent_students: int
    groups_created: int
    max_groups: int
    compressed: bool

class GroupingResponse(BaseModel):
    session_id: UUID
    target_competency: Optional[CompetencyRef] = None
    summary: GroupingSummary
    groups: List[LearningGroupResponse]
    excluded_students: List[ExcludedStudentResponse]
    warnings: List[str]

class GenerateGroupsRequest(BaseModel):
    replace_existing: bool = False
    force_replace_teacher_edits: bool = False

class MoveStudentRequest(BaseModel):
    student_id: UUID
    target_group_id: UUID
    reason: Optional[str] = None

class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    reason: Optional[str] = None
