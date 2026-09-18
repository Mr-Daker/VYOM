"""Core domain models for Saarthi-MG.

The models use only the Python standard library so the demo runs without a
framework. User-provided data is validated at the boundary and every
recommendation can be serialized to JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class LoopStep(str, Enum):
    ATTENDANCE = "Attendance"
    CURRENT_MASTERY = "Current student mastery"
    DETECT_GAPS = "Detect learning gaps"
    CREATE_GROUPS = "Create flexible groups"
    TEACHER_PRIORITY = "Decide teacher-attention priority"
    BUILD_ROTATION = "Build classroom rotation"
    GENERATE_ACTIVITIES = "Generate group activities"
    TEACHER_REVIEW = "Teacher reviews/edits"
    RUN_CLASS = "Run class"
    EXIT_CHECK = "Quick exit check"
    UPDATE_MASTERY = "Update mastery"
    REGROUP = "Regroup for next class"


LOOP_ORDER = list(LoopStep)


class MasteryState(str, Enum):
    NOT_YET = "Not yet learned"
    DEVELOPING = "Developing"
    MASTERED = "Mastered"


MASTERY_THRESHOLD_DEVELOPING = 0.40
MASTERY_THRESHOLD_MASTERED = 0.70


def validate_score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("mastery score must be a number")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError("mastery score must be between 0 and 1")
    return value


def score_to_state(score: float) -> MasteryState:
    score = validate_score(score)
    if score < MASTERY_THRESHOLD_DEVELOPING:
        return MasteryState.NOT_YET
    if score < MASTERY_THRESHOLD_MASTERED:
        return MasteryState.DEVELOPING
    return MasteryState.MASTERED


def validate_iso_date(value: str, field_name: str = "date") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc
    return value


def update_mastery_score(
    current_score: float,
    observation: Optional[str] = None,
    exit_ticket_correct: Optional[bool] = None,
    decay_days_since_last: int = 0,
) -> Tuple[float, str]:
    """Apply the transparent MVP evidence rule."""

    current_score = validate_score(current_score)
    if observation not in (None, "understood", "needs_practice", "not_assessed"):
        raise ValueError("observation must be understood, needs_practice, or not_assessed")
    if exit_ticket_correct not in (None, True, False):
        raise ValueError("exit_ticket_correct must be true, false, or null")

    delta = 0.0
    reasons: List[str] = []
    if observation == "understood":
        delta += 0.20
        reasons.append("teacher observed understanding (+0.20)")
    elif observation == "needs_practice":
        delta -= 0.15
        reasons.append("teacher observed a need for practice (-0.15)")

    if exit_ticket_correct is True:
        delta += 0.15
        reasons.append("exit check was correct (+0.15)")
    elif exit_ticket_correct is False:
        delta -= 0.10
        reasons.append("exit check was incorrect (-0.10)")

    if decay_days_since_last >= 7 and observation in (None, "not_assessed") and exit_ticket_correct is None:
        delta -= 0.05
        reasons.append(f"evidence is {decay_days_since_last} days old (-0.05; needs verification)")

    updated = round(max(0.0, min(1.0, current_score + delta)), 2)
    return updated, "; ".join(reasons) if reasons else "no new evidence; score unchanged"


@dataclass(frozen=True)
class Competency:
    id: str
    subject: str
    description: str
    grade_level: int
    prerequisites: List[str] = field(default_factory=list)


NUMERACY_COMPETENCIES = [
    Competency("N1", "Numeracy", "Count objects up to 20", 1, []),
    Competency("N2", "Numeracy", "Compare numbers using more, less, and equal", 1, ["N1"]),
    Competency("N3", "Numeracy", "Represent two-digit numbers as tens and ones", 2, ["N1", "N2"]),
    Competency("N4", "Numeracy", "Add two-digit numbers without regrouping", 2, ["N3"]),
    Competency("N5", "Numeracy", "Add two-digit numbers with regrouping", 2, ["N4"]),
    # For the demo, addition practice checks whether a returning learner can
    # compose/decompose quantities before moving into two-digit subtraction.
    Competency("N6", "Numeracy", "Subtract two-digit numbers without borrowing", 3, ["N3", "N4"]),
    Competency("N7", "Numeracy", "Subtract two-digit numbers with borrowing", 3, ["N5", "N6"]),
]

READING_COMPETENCIES = [
    Competency("R1", "Reading", "Recognise letters and their common sounds", 1, []),
    Competency("R2", "Reading", "Read common words", 1, ["R1"]),
    Competency("R3", "Reading", "Read simple sentences", 2, ["R2"]),
    Competency("R4", "Reading", "Read a short paragraph with fluency", 2, ["R3"]),
    Competency("R5", "Reading", "Answer literal questions about a paragraph", 3, ["R4"]),
]

ALL_COMPETENCIES: Dict[str, Competency] = {
    competency.id: competency
    for competency in NUMERACY_COMPETENCIES + READING_COMPETENCIES
}


@dataclass
class AttendanceEntry:
    date: str
    present: bool
    concepts_taught: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttendanceEntry":
        if not isinstance(data, dict):
            raise ValueError("attendance entry must be an object")
        present = data.get("present")
        if not isinstance(present, bool):
            raise ValueError("attendance present must be true or false")
        concepts = data.get("concepts_taught", [])
        if not isinstance(concepts, list) or not all(isinstance(item, str) for item in concepts):
            raise ValueError("concepts_taught must be a list of competency IDs")
        return cls(validate_iso_date(data.get("date"), "attendance date"), present, concepts)


@dataclass
class CompetencyRecord:
    competency_id: str
    score: float
    state: MasteryState
    last_assessed: Optional[str] = None
    missed: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompetencyRecord":
        if not isinstance(data, dict) or not isinstance(data.get("competency_id"), str):
            raise ValueError("competency record requires competency_id")
        score = validate_score(data.get("score"))
        state = MasteryState(data.get("state", score_to_state(score).value))
        last_assessed = data.get("last_assessed")
        if last_assessed is not None:
            validate_iso_date(last_assessed, "last_assessed")
        missed = data.get("missed", False)
        if not isinstance(missed, bool):
            raise ValueError("missed must be true or false")
        return cls(data["competency_id"], score, state, last_assessed, missed)


@dataclass
class Student:
    id: str
    name: str
    grade: int
    home_language: str
    attendance_history: List[AttendanceEntry] = field(default_factory=list)
    competencies: Dict[str, CompetencyRecord] = field(default_factory=dict)
    missed_concepts: List[str] = field(default_factory=list)
    teacher_notes: str = ""
    current_group: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Student":
        if not isinstance(data, dict):
            raise ValueError("student must be an object")
        for key in ("id", "name", "home_language"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ValueError(f"student {key} must be a non-empty string")
        grade = data.get("grade")
        if isinstance(grade, bool) or not isinstance(grade, int) or grade not in (1, 2, 3):
            raise ValueError("student grade must be 1, 2, or 3")
        raw_competencies = data.get("competencies", {})
        if not isinstance(raw_competencies, dict):
            raise ValueError("competencies must be an object")
        competencies = {
            competency_id: CompetencyRecord.from_dict(record)
            for competency_id, record in raw_competencies.items()
        }
        return cls(
            id=data["id"].strip(),
            name=data["name"].strip(),
            grade=grade,
            home_language=data["home_language"].strip(),
            attendance_history=[AttendanceEntry.from_dict(item) for item in data.get("attendance_history", [])],
            competencies=competencies,
            missed_concepts=list(data.get("missed_concepts", [])),
            teacher_notes=str(data.get("teacher_notes", "")),
            current_group=data.get("current_group"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)

    @property
    def mastery_summary(self) -> Dict[str, MasteryState]:
        return {competency_id: record.state for competency_id, record in self.competencies.items()}

    def has_prerequisite_gap(self, target_competency_id: str) -> List[str]:
        target = ALL_COMPETENCIES.get(target_competency_id)
        if not target:
            return []
        return [
            prerequisite_id
            for prerequisite_id in target.prerequisites
            if prerequisite_id not in self.competencies
            or self.competencies[prerequisite_id].state != MasteryState.MASTERED
        ]

    def was_present(self, on_date: str) -> Optional[bool]:
        for entry in reversed(self.attendance_history):
            if entry.date == on_date:
                return entry.present
        return None

    def returning_after_absence(self, on_date: str) -> bool:
        previous = [entry for entry in self.attendance_history if entry.date < on_date]
        return bool(previous and previous[-1].present is False and self.was_present(on_date) is not False)


class ActivityType(str, Enum):
    TEACHER_LED_EXPLANATION = "Teacher-led explanation"
    GUIDED_PRACTICE = "Guided practice"
    PEER_ACTIVITY = "Peer activity"
    INDEPENDENT_WORKSHEET = "Independent worksheet"
    MANIPULATIVE_ACTIVITY = "Local-material/manipulative activity"
    RECOVERY_ACTIVITY = "Recovery activity"
    EXTENSION_ACTIVITY = "Extension activity"
    EXIT_CHECK = "Exit check"


@dataclass
class LearningGroup:
    id: str
    name: str
    reason: str
    student_ids: List[str]
    target_competency_id: str
    focus_competency_id: str
    mastery_level: str
    scaffold_language: str = "English"
    language_breakdown: Dict[str, int] = field(default_factory=dict)
    priority_score: float = 0.0
    priority_factors: Dict[str, float] = field(default_factory=dict)
    priority_explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)


@dataclass
class Activity:
    id: str
    title: str
    objective: str
    activity_type: ActivityType
    competency_id: str
    target_level: str
    group_id: str
    duration_minutes: int
    materials_needed: List[str]
    teacher_involvement_required: bool
    student_instructions: List[str]
    expected_response: str
    quick_check: str
    source_reference: str
    language: str = "English"
    status: str = "draft"
    generated_by: str = "grounded-template"
    recovery_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)


@dataclass
class ExitTicket:
    id: str
    group_id: str
    competency_id: str
    question: str
    follow_up: str
    expected_answer: str
    language: str
    source_reference: str

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)


@dataclass
class TeacherObservation:
    student_id: str
    competency_id: str
    observation: str
    date: str

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)


@dataclass
class RotationSlot:
    slot_index: int
    start_minute: int
    end_minute: int
    group_id: str
    station: str
    activity: Activity

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)


@dataclass
class ClassSession:
    id: str
    date: str
    objective_competency_id: str
    total_duration_minutes: int
    groups: List[LearningGroup]
    rotation_slots: List[RotationSlot]
    available_materials: List[str]
    language: str
    teacher_approved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
