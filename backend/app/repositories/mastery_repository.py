from app.repositories.base import BaseRepository
from app.models.all_models import StudentMastery
from uuid import UUID

class MasteryRepository(BaseRepository):
    def get_for_students_and_competencies(self, student_ids: list[UUID], competency_ids: list[UUID]):
        if not student_ids or not competency_ids: return []
        return self.db.query(StudentMastery).filter(StudentMastery.student_id.in_(student_ids), StudentMastery.competency_id.in_(competency_ids)).all()

    def get_by_student_and_comp(self, student_id: UUID, comp_id: UUID) -> StudentMastery | None:
        return self.db.query(StudentMastery).filter(
            StudentMastery.student_id == student_id,
            StudentMastery.competency_id == comp_id
        ).first()
        
    def get_by_student(self, student_id: UUID):
        return self.db.query(StudentMastery).filter(StudentMastery.student_id == student_id).all()
        
    def add(self, mastery: StudentMastery):
        self.db.add(mastery)
        self.db.flush()
        return mastery

    def get_for_students(self, student_ids: list[UUID]):
        return self.db.query(StudentMastery).filter(StudentMastery.student_id.in_(student_ids)).all()
