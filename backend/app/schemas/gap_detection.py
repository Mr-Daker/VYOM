from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from app.models.enums import GapClassification, StudentAnalysisStatus, OverallReadinessStatus, MasteryState, AttendanceStatus

class PrerequisiteAssessment(BaseModel):
    competency_id: UUID
    competency_code: str
    competency_name: str
    relationship: str
    mastery_score: Optional[float] = None
    mastery_state: Optional[MasteryState] = None
    confidence: Optional[float] = None
    last_updated: Optional[str] = None
    stale: bool = False
    classification: GapClassification
    mastery_source: str = "none"
    relevant_sessions: int = 0
    present_sessions: int = 0
    absent_sessions: int = 0
    late_sessions: int = 0
    attendance_unrecorded_sessions: int = 0
    missed_instruction_risk: bool = False
    reasons: List[str] = Field(default_factory=list)

class StudentGapAssessment(BaseModel):
    student_id: UUID
    student_name: str
    grade: int
    current_attendance: Optional[AttendanceStatus] = None
    analysis_status: StudentAnalysisStatus
    overall_status: OverallReadinessStatus
    recovery_recommended: bool = False
    quick_check_recommended: bool = False
    assessment_recommended: bool = False
    direct_prerequisites: List[PrerequisiteAssessment] = Field(default_factory=list)
    transitive_context: List[PrerequisiteAssessment] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)

class GapDetectionSummary(BaseModel):
    students_total: int = 0
    students_analyzed: int = 0
    students_absent: int = 0
    attendance_unknown: int = 0
    ready: int = 0
    needs_support: int = 0
    needs_check: int = 0
    no_prerequisites: int = 0

class GapDetectionMetadata(BaseModel):
    attendance_lookback_days: int
    mastery_stale_days: int
    warnings: List[str] = Field(default_factory=list)

class GapDetectionResponse(BaseModel):
    session_id: UUID
    classroom_id: UUID
    target_competency_id: Optional[UUID] = None
    metadata: GapDetectionMetadata
    summary: GapDetectionSummary
    students: List[StudentGapAssessment] = Field(default_factory=list)
