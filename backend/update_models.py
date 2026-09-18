with open("app/models/enums.py", "r") as f:
    content = f.read()

if "GroupType" not in content:
    content += """
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
"""
    with open("app/models/enums.py", "w") as f:
        f.write(content)

with open("app/models/all_models.py", "r") as f:
    models_content = f.read()

if "LearningGroup" not in models_content:
    models_content += """
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    group = relationship("LearningGroup", backref="memberships")
    student = relationship("Student")
    focus_competency = relationship("Competency")

    __table_args__ = (
        UniqueConstraint('session_id', 'student_id', name='uq_membership_session_student'),
        UniqueConstraint('group_id', 'student_id', name='uq_membership_group_student'),
    )
"""
    with open("app/models/all_models.py", "w") as f:
        f.write(models_content)

