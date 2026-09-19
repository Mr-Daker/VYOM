import json
import uuid
from datetime import datetime, timezone
from sqlalchemy.sql import func
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, JSON, Boolean, UniqueConstraint, CheckConstraint, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
from app.models.enums import UserRole, MasteryState, EvidenceSource, AttendanceStatus, SessionStatus, RotationSlotType

def utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole, name="userrole", values_callable=lambda x: [e.value for e in x]), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    classrooms = relationship("Classroom", back_populates="teacher")

class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    school_name = Column(String)
    default_language = Column(String)
    secondary_language = Column(String)
    default_duration_minutes = Column(Integer)
    max_groups = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint('default_duration_minutes > 0', name='check_duration_positive'),
        CheckConstraint('max_groups > 0', name='check_groups_positive'),
    )

    teacher = relationship("User", back_populates="classrooms")
    students = relationship("Student", back_populates="classroom", cascade="all, delete-orphan")
    sessions = relationship("ClassSession", back_populates="classroom", cascade="all, delete-orphan")

class Student(Base):
    __tablename__ = "students"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classroom_id = Column(UUID(as_uuid=True), ForeignKey("classrooms.id"), nullable=False)
    name = Column(String, nullable=False)
    grade = Column(Integer, nullable=False)
    preferred_language = Column(String)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint('grade IN (1, 2, 3)', name='check_valid_grade'),
    )

    classroom = relationship("Classroom", back_populates="students")
    attendance_records = relationship("AttendanceRecord", back_populates="student", cascade="all, delete-orphan")
    mastery_records = relationship("StudentMastery", back_populates="student", cascade="all, delete-orphan")
    evidence_records = relationship("MasteryEvidence", back_populates="student", cascade="all, delete-orphan")

class Competency(Base):
    __tablename__ = "competencies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String, unique=True, nullable=False)
    subject = Column(String, nullable=False)
    grade = Column(Integer)
    name = Column(String, nullable=False)
    description = Column(String)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint('grade IN (1, 2, 3)', name='check_comp_grade'),
    )

class CompetencyPrerequisite(Base):
    __tablename__ = "competency_prerequisites"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    prerequisite_competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        UniqueConstraint('competency_id', 'prerequisite_competency_id', name='uq_competency_prerequisite'),
        CheckConstraint('competency_id != prerequisite_competency_id', name='check_no_self_prerequisite')
    )

class StudentMastery(Base):
    __tablename__ = "student_mastery"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    score = Column(Float, nullable=False)
    state = Column(Enum(MasteryState, name="masterystate", values_callable=lambda x: [e.value for e in x]), nullable=False)
    confidence = Column(Float)
    last_updated = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint('student_id', 'competency_id', name='uq_student_competency_mastery'),
        CheckConstraint('score >= 0 AND score <= 1', name='check_mastery_score_bounds'),
        CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='check_mastery_confidence_bounds')
    )

    student = relationship("Student", back_populates="mastery_records")

class MasteryEvidence(Base):
    __tablename__ = "mastery_evidence"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id"), nullable=True)
    source_type = Column(Enum(EvidenceSource, name="evidencesource", values_callable=lambda x: [e.value for e in x]), nullable=False)
    score = Column(Float, nullable=False)
    confidence = Column(Float)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (
        CheckConstraint('score >= 0 AND score <= 1', name='check_evidence_score_bounds'),
        CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='check_evidence_confidence_bounds')
    )

    student = relationship("Student", back_populates="evidence_records")
    session = relationship("ClassSession", back_populates="evidence_records")

class ClassSession(Base):
    __tablename__ = "class_sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classroom_id = Column(UUID(as_uuid=True), ForeignKey("classrooms.id"), nullable=False)
    date = Column(DateTime(timezone=True), default=utc_now)
    subject = Column(String)
    target_competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=True)
    duration_minutes = Column(Integer)
    available_materials = Column(JSON)
    status = Column(Enum(SessionStatus, name='session_status_enum', native_enum=False), default=SessionStatus.DRAFT, nullable=False)
    grouping_warnings = Column(JSON, nullable=True)
    grouping_compressed = Column(Boolean, nullable=False, default=False)
    groups_teacher_modified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    priority_generated_at = Column(DateTime(timezone=True), nullable=True)
    priority_stale = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint('duration_minutes > 0', name='check_session_duration'),
    )

    classroom = relationship("Classroom", back_populates="sessions")
    attendance_records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")
    evidence_records = relationship("MasteryEvidence", back_populates="session")

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    class_session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id"), nullable=False)
    status = Column(Enum(AttendanceStatus, name="attendancestatus", values_callable=lambda x: [e.value for e in x]), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint('student_id', 'class_session_id', name='uq_student_session_attendance'),
    )

    student = relationship("Student", back_populates="attendance_records")
    session = relationship("ClassSession", back_populates="attendance_records")

from app.models.enums import GroupType, CheckMode

class LearningGroup(Base):
    __tablename__ = 'learning_groups'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('class_sessions.id', ondelete='CASCADE'), nullable=False)
    name = Column(String, nullable=False)
    group_type = Column(Enum(GroupType, name='group_type_enum', native_enum=False), nullable=False)
    focus_competency_id = Column(UUID(as_uuid=True), ForeignKey('competencies.id', ondelete='SET NULL'), nullable=True)
    check_mode = Column(Enum(CheckMode, name='check_mode_enum', native_enum=False), nullable=True)
    reason = Column(String, nullable=False)
    mixed_needs = Column(Boolean, nullable=False, default=False)
    teacher_modified = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("ClassSession", backref="learning_groups")
    focus_competency = relationship("Competency")

class GroupMembership(Base):
    __tablename__ = 'group_memberships'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('class_sessions.id', ondelete='CASCADE'), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey('learning_groups.id', ondelete='CASCADE'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    focus_competency_id = Column(UUID(as_uuid=True), ForeignKey('competencies.id', ondelete='SET NULL'), nullable=True)
    assignment_reason = Column(String, nullable=False)
    original_group_type = Column(String, nullable=True)
    original_check_mode = Column(String, nullable=True)
    teacher_override_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    group = relationship("LearningGroup", backref="memberships")
    student = relationship("Student")
    focus_competency = relationship("Competency")

    __table_args__ = (
        UniqueConstraint('session_id', 'student_id', name='uq_membership_session_student'),
        UniqueConstraint('group_id', 'student_id', name='uq_membership_group_student'),
    )

class GroupPriority(Base):
    __tablename__ = 'group_priorities'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('class_sessions.id'), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey('learning_groups.id', ondelete="CASCADE"), nullable=False)
    
    priority_score = Column(Float, nullable=False)
    priority_rank = Column(Integer, nullable=False)
    priority_tier = Column(String, nullable=False)
    
    teacher_rank = Column(Integer, nullable=True)
    teacher_override_reason = Column(String, nullable=True)
    
    instructional_need_score = Column(Float, nullable=False)
    evidence_severity_score = Column(Float, nullable=False)
    uncertainty_score = Column(Float, nullable=False)
    missed_instruction_score = Column(Float, nullable=False)
    group_complexity_score = Column(Float, nullable=False)
    reach_score = Column(Float, nullable=False)
    
    factor_breakdown = Column(JSON, nullable=False)
    reasons = Column(JSON, nullable=False)
    top_reason = Column(String, nullable=False)
    
    student_count_at_generation = Column(Integer, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    
    group = relationship("LearningGroup")
    
    __table_args__ = (
        UniqueConstraint('session_id', 'group_id', name='uq_priority_session_group'),
        UniqueConstraint('session_id', 'priority_rank', name='uq_priority_session_rank'),
        CheckConstraint('priority_score >= 0 AND priority_score <= 100', name='chk_priority_score_range'),
        CheckConstraint('priority_rank > 0', name='chk_priority_rank_positive'),
        CheckConstraint('teacher_rank IS NULL OR teacher_rank > 0', name='chk_teacher_rank_positive'),
        CheckConstraint('instructional_need_score >= 0', name='chk_instructional_need_positive'),
        CheckConstraint('evidence_severity_score >= 0', name='chk_evidence_severity_positive'),
        CheckConstraint('uncertainty_score >= 0', name='chk_uncertainty_positive'),
        CheckConstraint('missed_instruction_score >= 0', name='chk_missed_instruction_positive'),
        CheckConstraint('group_complexity_score >= 0', name='chk_group_complexity_positive'),
        CheckConstraint('reach_score >= 0', name='chk_reach_positive'),
        CheckConstraint("priority_tier IN ('urgent', 'high', 'moderate', 'low')", name='chk_priority_tier'),
        CheckConstraint('student_count_at_generation > 0', name='chk_student_count_gen_positive'),
    )


class RotationPlan(Base):
    __tablename__ = "rotation_plans"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False)
    
    session_duration_minutes = Column(Integer, nullable=False)
    opening_minutes = Column(Integer, nullable=False)
    closing_minutes = Column(Integer, nullable=False)
    transition_minutes_each = Column(Integer, nullable=False)
    transition_total_minutes = Column(Integer, nullable=False)
    teacher_attention_budget_minutes = Column(Integer, nullable=False)
    minimum_group_attention_minutes = Column(Integer, nullable=False)
    group_count = Column(Integer, nullable=False)
    algorithm_version = Column(String, nullable=False)
    
    generated_at = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint('session_id', name='uq_rotation_plan_session_id'),
        CheckConstraint('session_duration_minutes > 0', name='chk_rp_session_duration'),
        CheckConstraint('opening_minutes >= 0', name='chk_rp_opening_minutes'),
        CheckConstraint('closing_minutes >= 0', name='chk_rp_closing_minutes'),
        CheckConstraint('transition_minutes_each >= 0', name='chk_rp_trans_min_each'),
        CheckConstraint('transition_total_minutes >= 0', name='chk_rp_trans_total'),
        CheckConstraint('teacher_attention_budget_minutes > 0', name='chk_rp_budget'),
        CheckConstraint('minimum_group_attention_minutes > 0', name='chk_rp_min_group_attention'),
        CheckConstraint('group_count > 0', name='chk_rp_group_count'),
    )

class RotationSlot(Base):
    __tablename__ = "rotation_slots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rotation_plan_id = Column(UUID(as_uuid=True), ForeignKey("rotation_plans.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False)
    
    sequence_index = Column(Integer, nullable=False)
    slot_type = Column(Enum(RotationSlotType, name="rotationslottype", values_callable=lambda x: [e.value for e in x]), nullable=False)
    
    group_id = Column(UUID(as_uuid=True), ForeignKey("learning_groups.id", ondelete="RESTRICT"), nullable=True)
    
    start_minute = Column(Integer, nullable=False)
    end_minute = Column(Integer, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    
    group_name_snapshot = Column(String, nullable=True)
    group_type_snapshot = Column(String, nullable=True)
    
    priority_score_snapshot = Column(Float, nullable=True)
    algorithm_priority_rank_snapshot = Column(Integer, nullable=True)
    teacher_rank_snapshot = Column(Integer, nullable=True)
    effective_rank_snapshot = Column(Integer, nullable=True)
    
    student_count_snapshot = Column(Integer, nullable=True)
    
    base_minutes = Column(Integer, nullable=True)
    weighted_extra_minutes = Column(Integer, nullable=True)
    reason = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint('rotation_plan_id', 'sequence_index', name='uq_rotation_slot_seq'),
        CheckConstraint('sequence_index >= 0', name='chk_rs_seq_index'),
        CheckConstraint('start_minute >= 0', name='chk_rs_start_minute'),
        CheckConstraint('end_minute > start_minute', name='chk_rs_end_gt_start'),
        CheckConstraint('duration_minutes > 0', name='chk_rs_duration_gt_zero'),
        CheckConstraint('duration_minutes = end_minute - start_minute', name='chk_rs_duration_calc'),
        CheckConstraint(
            "(slot_type = 'group_visit' AND group_id IS NOT NULL) OR (slot_type != 'group_visit' AND group_id IS NULL)", 
            name='chk_rs_group_id_semantics'
        ),
        CheckConstraint(
            "(slot_type != 'group_visit') OR ("
            "group_id IS NOT NULL AND "
            "group_name_snapshot IS NOT NULL AND "
            "group_type_snapshot IS NOT NULL AND "
            "priority_score_snapshot IS NOT NULL AND "
            "priority_score_snapshot >= 0 AND "
            "priority_score_snapshot <= 100 AND "
            "algorithm_priority_rank_snapshot IS NOT NULL AND "
            "algorithm_priority_rank_snapshot > 0 AND "
            "effective_rank_snapshot IS NOT NULL AND "
            "effective_rank_snapshot > 0 AND "
            "student_count_snapshot IS NOT NULL AND "
            "student_count_snapshot > 0 AND "
            "base_minutes IS NOT NULL AND "
            "base_minutes > 0 AND "
            "weighted_extra_minutes IS NOT NULL AND "
            "weighted_extra_minutes >= 0 AND "
            "reason IS NOT NULL"
            ")",
            name='chk_rs_group_visit_snapshot'
        ),
    )


# --- Curriculum Knowledge Base Models ---

from sqlalchemy.types import UserDefinedType, TypeDecorator, Text
from app.core.curriculum_config import CURRICULUM_EMBEDDING_DIMENSION

class PGVector(UserDefinedType):
    cache_ok = True
    def __init__(self, dim):
        self.dim = dim

    def get_col_spec(self, **kw):
        return f"vector({self.dim})"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return "[" + ",".join(str(float(v)) for v in value) + "]"
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return json.loads(value)
            return value
        return process

class FallbackVector(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, dim):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGVector(self.dim))
        else:
            return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.dumps([float(v) for v in value])

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return json.loads(value)


class CurriculumDocument(Base):
    __tablename__ = "curriculum_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    grade_min = Column(Integer, nullable=True)
    grade_max = Column(Integer, nullable=True)
    language = Column(String, nullable=False)
    version = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    status = Column(String, nullable=False)
    embedding_status = Column(String, nullable=False)
    original_filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("checksum", name="uq_curr_doc_checksum"),
        CheckConstraint("grade_min >= 1", name="chk_curr_doc_grade_min"),
        CheckConstraint("grade_max >= 1", name="chk_curr_doc_grade_max"),
        CheckConstraint("grade_min <= grade_max", name="chk_curr_doc_grade_order"),
        CheckConstraint("source_type IN ('teacher_upload', 'curriculum_framework', 'textbook', 'teacher_guide', 'reference')", name="chk_curr_doc_source_type"),
        CheckConstraint("status IN ('draft', 'processing', 'ready', 'failed', 'archived')", name="chk_curr_doc_status"),
        CheckConstraint("embedding_status IN ('not_requested', 'pending', 'ready', 'failed')", name="chk_curr_doc_embedding_status"),
    )


class CurriculumChunk(Base):
    __tablename__ = "curriculum_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("curriculum_documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(String, nullable=False)
    text_hash = Column(String, nullable=False)
    token_count = Column(Integer, nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    section_title = Column(String, nullable=True)
    embedding = Column(FallbackVector(CURRICULUM_EMBEDDING_DIMENSION), nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_curr_chunk_doc_idx"),
        CheckConstraint("chunk_index >= 0", name="chk_curr_chunk_idx_pos"),
        CheckConstraint("length(trim(text)) > 0", name="chk_curr_chunk_text_nonblank"),
        CheckConstraint("page_start IS NULL OR page_start >= 1", name="chk_curr_chunk_page_start"),
        CheckConstraint("page_end IS NULL OR page_end >= 1", name="chk_curr_chunk_page_end"),
        CheckConstraint("page_start IS NULL OR page_end IS NULL OR page_start <= page_end", name="chk_curr_chunk_page_order"),
    )


class CurriculumChunkCompetency(Base):
    __tablename__ = "curriculum_chunk_competencies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("curriculum_chunks.id"), nullable=False)
    competency_id = Column(UUID(as_uuid=True), ForeignKey("competencies.id"), nullable=False)
    mapping_type = Column(String, nullable=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("chunk_id", "competency_id", name="uq_curr_map_chunk_comp"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="chk_curr_map_confidence"),
    )

class ActivityPlan(Base):
    __tablename__ = 'activity_plans'
    __table_args__ = (
        UniqueConstraint('session_id', name='uq_activity_plan_session'),
        CheckConstraint("status = 'draft'", name='chk_activity_plan_status'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey('class_sessions.id'), nullable=False)
    prompt_version = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    language = Column(String, nullable=False, default="en")
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    group_activities = relationship("GroupActivity", back_populates="plan", cascade="all, delete-orphan")

class GroupActivity(Base):
    __tablename__ = 'group_activities'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_plan_id = Column(UUID(as_uuid=True), ForeignKey('activity_plans.id'), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey('class_sessions.id'), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey('learning_groups.id'), nullable=False)
    
    group_name_snapshot = Column(String, nullable=False)
    group_type_snapshot = Column(String, nullable=False)
    focus_competency_id = Column(UUID(as_uuid=True), ForeignKey('competencies.id'), nullable=False)
    
    title = Column(String, nullable=False)
    objective = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    teacher_attention_minutes = Column(Integer, nullable=False)
    independent_minutes = Column(Integer, nullable=False)
    
    materials = Column(JSON, nullable=False)
    teacher_actions = Column(JSON, nullable=False)
    student_actions = Column(JSON, nullable=False)
    checks_for_understanding = Column(JSON, nullable=False)
    success_criteria = Column(JSON, nullable=False)
    adaptations = Column(JSON, nullable=False)
    
    generated_by = Column(String, nullable=False, default="llm")
    approval_status = Column(String, nullable=False, default="pending_teacher_review")
    prompt_version = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    prompt_input_hash = Column(String, nullable=False)
    structured_output_hash = Column(String, nullable=False)
    generation_order = Column(Integer, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    plan = relationship("ActivityPlan", back_populates="group_activities")
    citations = relationship("ActivitySourceCitation", back_populates="group_activity", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint('activity_plan_id', 'group_id', name='uq_grp_act_plan_group'),
        CheckConstraint('duration_minutes > 0', name='chk_grp_act_duration'),
        CheckConstraint('teacher_attention_minutes >= 0', name='chk_grp_act_teacher_min'),
        CheckConstraint('independent_minutes >= 0', name='chk_grp_act_indep_min'),
        CheckConstraint("approval_status = 'pending_teacher_review'", name='chk_grp_act_approval'),
        CheckConstraint("generated_by = 'llm'", name='chk_grp_act_generated_by'),
        CheckConstraint('generation_order >= 0', name='chk_grp_act_generation_order'),
        UniqueConstraint('activity_plan_id', 'generation_order', name='uq_grp_act_plan_order')
    )

class ActivitySourceCitation(Base):
    __tablename__ = 'activity_source_citations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_activity_id = Column(UUID(as_uuid=True), ForeignKey('group_activities.id'), nullable=False)
    curriculum_chunk_id = Column(UUID(as_uuid=True), ForeignKey('curriculum_chunks.id'), nullable=False)
    citation_order = Column(Integer, nullable=False)
    
    # Snapshots for historical reading even if chunk is deleted/archived
    document_id_snapshot = Column(UUID(as_uuid=True), nullable=False)
    document_title_snapshot = Column(String, nullable=False)
    source_name_snapshot = Column(String, nullable=False)
    source_type_snapshot = Column(String, nullable=False)
    version_snapshot = Column(String, nullable=False)
    section_title_snapshot = Column(String, nullable=True)
    page_start_snapshot = Column(Integer, nullable=True)
    page_end_snapshot = Column(Integer, nullable=True)
    chunk_index_snapshot = Column(Integer, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utc_now)
    
    group_activity = relationship("GroupActivity", back_populates="citations")
    
    __table_args__ = (
        UniqueConstraint('group_activity_id', 'curriculum_chunk_id', name='uq_act_cit_activity_chunk'),
        CheckConstraint('citation_order >= 0', name='chk_act_cit_order')
    )
