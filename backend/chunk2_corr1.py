import os

with open("app/core/config.py", "w") as f:
    f.write("""import os

class Settings:
    MASTERY_STALE_DAYS: int = int(os.getenv("MASTERY_STALE_DAYS", "30"))
    GAP_ATTENDANCE_LOOKBACK_DAYS: int = int(os.getenv("GAP_ATTENDANCE_LOOKBACK_DAYS", "30"))
    
settings = Settings()
""")

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

with open("app/repositories/mastery_repository.py", "r") as f:
    content = f.read()

# Add get_for_students_and_competencies
if "get_for_students_and_competencies" not in content:
    content = content.replace(
        "class MasteryRepository(BaseRepository):",
        "class MasteryRepository(BaseRepository):\n"
        "    def get_for_students_and_competencies(self, student_ids: list[UUID], competency_ids: list[UUID]):\n"
        "        if not student_ids or not competency_ids: return []\n"
        "        return self.db.query(StudentMastery).filter(StudentMastery.student_id.in_(student_ids), StudentMastery.competency_id.in_(competency_ids)).all()\n"
    )
    with open("app/repositories/mastery_repository.py", "w") as f:
        f.write(content)

with open("app/repositories/session_repository.py", "r") as f:
    content = f.read()

if "since_date" not in content:
    # We replace get_completed_before to accept since_date
    import re
    content = re.sub(
        r"def get_completed_before.*?all\(\)",
        "def get_completed_before(self, classroom_id: UUID, before_date, since_date, target_competency_ids: list[UUID]):\n"
        "        from app.models.enums import SessionStatus\n"
        "        if not target_competency_ids: return []\n"
        "        return self.db.query(ClassSession).filter(\n"
        "            ClassSession.classroom_id == classroom_id,\n"
        "            ClassSession.date < before_date,\n"
        "            ClassSession.date >= since_date,\n"
        "            ClassSession.target_competency_id.in_(target_competency_ids),\n"
        "            ClassSession.status == SessionStatus.COMPLETED\n"
        "        ).all()",
        content, flags=re.DOTALL
    )
    with open("app/repositories/session_repository.py", "w") as f:
        f.write(content)

