import re

with open("app/repositories/mastery_repository.py", "r") as f:
    content = f.read()
if "def get_for_students" not in content:
    content += """
    def get_for_students(self, student_ids: list[UUID]):
        return self.db.query(StudentMastery).filter(StudentMastery.student_id.in_(student_ids)).all()
"""
    with open("app/repositories/mastery_repository.py", "w") as f: f.write(content)

with open("app/repositories/session_repository.py", "r") as f:
    content = f.read()
if "def get_completed_before" not in content:
    content += """
    def get_completed_before(self, classroom_id: UUID, before_date, target_competency_ids: list[UUID]):
        from app.models.enums import SessionStatus
        return self.db.query(ClassSession).filter(
            ClassSession.classroom_id == classroom_id,
            ClassSession.date < before_date,
            ClassSession.target_competency_id.in_(target_competency_ids),
            ClassSession.status == SessionStatus.COMPLETED
        ).all()
"""
    with open("app/repositories/session_repository.py", "w") as f: f.write(content)

with open("app/repositories/attendance_repository.py", "r") as f:
    content = f.read()
if "def get_for_students_and_sessions" not in content:
    content += """
    def get_for_students_and_sessions(self, student_ids: list[UUID], session_ids: list[UUID]):
        if not student_ids or not session_ids: return []
        return self.db.query(AttendanceRecord).filter(
            AttendanceRecord.student_id.in_(student_ids),
            AttendanceRecord.class_session_id.in_(session_ids)
        ).all()
"""
    with open("app/repositories/attendance_repository.py", "w") as f: f.write(content)

with open("app/repositories/competency_repository.py", "r") as f:
    content = f.read()
if "def get_all_prerequisites" not in content:
    content += """
    def get_all_prerequisites(self):
        from app.models.all_models import CompetencyPrerequisite
        return self.db.query(CompetencyPrerequisite).all()
"""
    with open("app/repositories/competency_repository.py", "w") as f: f.write(content)
