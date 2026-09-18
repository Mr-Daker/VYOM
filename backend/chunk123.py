import os
import shutil

# 1. Update Models & Enums
with open("app/models/enums.py", "w") as f:
    f.write("""import enum

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
""")

with open("app/models/all_models.py", "w") as f:
    f.write("""import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, JSON, Boolean, UniqueConstraint, CheckConstraint, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
from app.models.enums import UserRole, MasteryState, EvidenceSource, AttendanceStatus, SessionStatus

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
    status = Column(Enum(SessionStatus, name="sessionstatus", values_callable=lambda x: [e.value for e in x]), nullable=False, default=SessionStatus.DRAFT)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

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
""")

# 2. Alembic Migration (Manual)
os.makedirs("alembic/versions", exist_ok=True)
with open("alembic/versions/001_initial.py", "w") as f:
    f.write("""\"\"\"Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-09-17 12:00:00.000000

\"\"\"
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    userrole = ENUM('teacher', 'admin', name='userrole', create_type=False)
    userrole.create(op.get_bind(), checkfirst=True)
    op.create_table('users',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', userrole, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    op.create_table('competencies',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.CheckConstraint('grade IN (1, 2, 3)', name='check_comp_grade')
    )

    op.create_table('classrooms',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('teacher_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('school_name', sa.String(), nullable=True),
        sa.Column('default_language', sa.String(), nullable=True),
        sa.Column('secondary_language', sa.String(), nullable=True),
        sa.Column('default_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('max_groups', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('default_duration_minutes > 0', name='check_duration_positive'),
        sa.CheckConstraint('max_groups > 0', name='check_groups_positive')
    )

    op.create_table('competency_prerequisites',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('prerequisite_competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['prerequisite_competency_id'], ['competencies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('competency_id', 'prerequisite_competency_id', name='uq_competency_prerequisite'),
        sa.CheckConstraint('competency_id != prerequisite_competency_id', name='check_no_self_prerequisite')
    )

    op.create_table('students',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('classroom_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=False),
        sa.Column('preferred_language', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('grade IN (1, 2, 3)', name='check_valid_grade')
    )

    masterystate = ENUM('unknown', 'needs_support', 'developing', 'mastered', name='masterystate', create_type=False)
    masterystate.create(op.get_bind(), checkfirst=True)
    op.create_table('student_mastery',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', UUID(as_uuid=True), nullable=False),
        sa.Column('competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('state', masterystate, nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'competency_id', name='uq_student_competency_mastery'),
        sa.CheckConstraint('score >= 0 AND score <= 1', name='check_mastery_score_bounds'),
        sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='check_mastery_confidence_bounds')
    )

    sessionstatus = ENUM('draft', 'attendance_recorded', 'grouped', 'scheduled', 'activities_ready', 'teacher_approved', 'in_progress', 'completed', name='sessionstatus', create_type=False)
    sessionstatus.create(op.get_bind(), checkfirst=True)
    op.create_table('class_sessions',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('classroom_id', UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('target_competency_id', UUID(as_uuid=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('available_materials', sa.JSON(), nullable=True),
        sa.Column('status', sessionstatus, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id'], ),
        sa.ForeignKeyConstraint(['target_competency_id'], ['competencies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('duration_minutes > 0', name='check_session_duration')
    )

    evidencesource = ENUM('initial_assessment', 'exit_ticket', 'teacher_observation', 'manual_assessment', name='evidencesource', create_type=False)
    evidencesource.create(op.get_bind(), checkfirst=True)
    op.create_table('mastery_evidence',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', UUID(as_uuid=True), nullable=False),
        sa.Column('competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True), nullable=True),
        sa.Column('source_type', evidencesource, nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('score >= 0 AND score <= 1', name='check_evidence_score_bounds'),
        sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='check_evidence_confidence_bounds')
    )

    attendancestatus = ENUM('present', 'absent', 'late', name='attendancestatus', create_type=False)
    attendancestatus.create(op.get_bind(), checkfirst=True)
    op.create_table('attendance_records',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', UUID(as_uuid=True), nullable=False),
        sa.Column('class_session_id', UUID(as_uuid=True), nullable=False),
        sa.Column('status', attendancestatus, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['class_session_id'], ['class_sessions.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'class_session_id', name='uq_student_session_attendance')
    )


def downgrade() -> None:
    op.drop_table('attendance_records')
    op.drop_table('mastery_evidence')
    op.drop_table('class_sessions')
    op.drop_table('student_mastery')
    op.drop_table('students')
    op.drop_table('competency_prerequisites')
    op.drop_table('classrooms')
    op.drop_table('competencies')
    op.drop_table('users')
    
    op.execute('DROP TYPE attendancestatus')
    op.execute('DROP TYPE evidencesource')
    op.execute('DROP TYPE sessionstatus')
    op.execute('DROP TYPE masterystate')
    op.execute('DROP TYPE userrole')
""")

