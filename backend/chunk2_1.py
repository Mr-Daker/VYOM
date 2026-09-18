with open("app/models/enums.py", "a") as f:
    f.write("""
class GapClassification(str, enum.Enum):
    READY = "ready"
    CONFIRMED_GAP = "confirmed_gap"
    LIKELY_GAP = "likely_gap"
    DEVELOPING = "developing"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class StudentAnalysisStatus(str, enum.Enum):
    ANALYZED = "analyzed"
    NOT_CURRENTLY_AVAILABLE = "not_currently_available"
    CURRENT_ATTENDANCE_UNKNOWN = "current_attendance_unknown"

class OverallReadinessStatus(str, enum.Enum):
    READY = "ready"
    NEEDS_SUPPORT = "needs_support"
    NEEDS_CHECK = "needs_check"
    NO_PREREQUISITES = "no_prerequisites"
    NOT_ANALYZED = "not_analyzed"
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
    relationship: str # "direct" or "transitive"
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
    missed_instruction_risk: bool = False
    reasons: List[str] = []

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
    direct_prerequisites: List[PrerequisiteAssessment] = []
    transitive_context: List[PrerequisiteAssessment] = []
    reasons: List[str] = []

class GapDetectionSummary(BaseModel):
    students_total: int = 0
    students_analyzed: int = 0
    students_absent: int = 0
    attendance_unknown: int = 0
    ready: int = 0
    needs_support: int = 0
    needs_check: int = 0
    no_prerequisites: int = 0

class GapDetectionResponse(BaseModel):
    session_id: UUID
    classroom_id: UUID
    target_competency_id: Optional[UUID] = None
    students: List[StudentGapAssessment] = []
    summary: GapDetectionSummary
""")

with open("app/api/routes/gaps.py", "w") as f:
    f.write("""from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.gap_detection_service import GapDetectionService
from app.schemas.gap_detection import GapDetectionResponse
from uuid import UUID

router = APIRouter()

@router.post("/sessions/{session_id}/detect-gaps", response_model=GapDetectionResponse)
def detect_gaps(session_id: UUID, db: Session = Depends(get_db)):
    return GapDetectionService(db).detect_gaps(session_id)
""")

import os
with open("app/api/router.py", "r") as f:
    content = f.read()
if "gaps.router" not in content:
    content = content.replace("from app.api.routes import health, classrooms, students, competencies, mastery, sessions, attendance",
                              "from app.api.routes import health, classrooms, students, competencies, mastery, sessions, attendance, gaps")
    content += "api_router.include_router(gaps.router, tags=[\"gap_detection\"])\n"
    with open("app/api/router.py", "w") as f:
        f.write(content)
