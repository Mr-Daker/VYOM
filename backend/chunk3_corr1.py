with open("app/schemas/gap_detection.py", "w") as f:
    f.write("""from pydantic import BaseModel, Field
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
""")

with open("app/repositories/evidence_repository.py", "w") as f:
    f.write("""from app.repositories.base import BaseRepository
from app.models.all_models import MasteryEvidence
from uuid import UUID

class EvidenceRepository(BaseRepository):
    def add(self, evidence: MasteryEvidence):
        self.db.add(evidence)
        self.db.flush()
        return evidence

    def get_latest_before_for_students_and_competencies(self, student_ids: list[UUID], competency_ids: list[UUID], before_date):
        if not student_ids or not competency_ids: return []
        # We fetch all matching evidence and group/sort in python, or use a distinct-on/window function.
        # Since sqlite and postgres differ on distinct ON, we'll fetch all and filter the latest in python to keep it DB-agnostic.
        records = self.db.query(MasteryEvidence).filter(
            MasteryEvidence.student_id.in_(student_ids),
            MasteryEvidence.competency_id.in_(competency_ids),
            MasteryEvidence.created_at <= before_date
        ).order_by(MasteryEvidence.created_at.desc()).all()
        
        result = {}
        for r in records:
            key = (r.student_id, r.competency_id)
            if key not in result:
                result[key] = r
        return list(result.values())
""")

