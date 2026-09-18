import enum

class UserRole(str, enum.Enum):
    TEACHER = "teacher"
    ADMIN = "admin"

class MasteryState(str, enum.Enum):
    UNKNOWN = "unknown"
    NEEDS_SUPPORT = "needs_support"
    DEVELOPING = "developing"
    MASTERED = "mastered"

class EvidenceSource(str, enum.Enum):
    INITIAL_ASSESSMENT = "initial_assessment"
    EXIT_TICKET = "exit_ticket"
    TEACHER_OBSERVATION = "teacher_observation"
    MANUAL_ASSESSMENT = "manual_assessment"

class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"

class SessionStatus(str, enum.Enum):
    DRAFT = "draft"
    ATTENDANCE_RECORDED = "attendance_recorded"
    GROUPED = "grouped"
    SCHEDULED = "scheduled"
    ACTIVITIES_READY = "activities_ready"
    TEACHER_APPROVED = "teacher_approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

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

class GroupType(str, enum.Enum):
    RECOVERY = "recovery"
    CHECK = "check"
    GUIDED = "guided"
    PRACTICE = "practice"
    EXTENSION = "extension"
    MIXED_SUPPORT = "mixed_support"

class CheckMode(str, enum.Enum):
    ASSESSMENT = "assessment"
    QUICK_CHECK = "quick_check"

class RotationSlotType(str, enum.Enum):
    WHOLE_CLASS_OPENING = "whole_class_opening"
    GROUP_VISIT = "group_visit"
    TRANSITION = "transition"
    WHOLE_CLASS_CLOSING = "whole_class_closing"
