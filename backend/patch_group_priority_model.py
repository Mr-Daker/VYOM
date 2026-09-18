import re

with open("app/models/all_models.py", "r") as f:
    content = f.read()

# Add CheckConstraint and UniqueConstraint to imports if not there
if "CheckConstraint" not in content:
    content = content.replace("from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Enum, JSON, Float", 
                              "from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, Enum, JSON, Float, CheckConstraint, UniqueConstraint")

# Find GroupPriority and patch it
pattern = re.compile(r'class GroupPriority\(Base\):.*?group = relationship\("LearningGroup"\)', re.DOTALL)

new_group_priority = """class GroupPriority(Base):
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
    )"""

content = pattern.sub(new_group_priority, content)

with open("app/models/all_models.py", "w") as f:
    f.write(content)
