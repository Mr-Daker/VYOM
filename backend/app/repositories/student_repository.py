from app.repositories.base import BaseRepository
from app.models.all_models import Student
from uuid import UUID

class StudentRepository(BaseRepository):
    def get_by_id(self, student_id: UUID) -> Student | None:
        return self.db.query(Student).filter(Student.id == student_id).first()
        
    def get_by_classroom(self, classroom_id: UUID):
        return self.db.query(Student).filter(Student.classroom_id == classroom_id).all()
        
    def add(self, student: Student):
        self.db.add(student)
        self.db.flush()
        return student
        
    def add_all(self, students: list[Student]):
        self.db.add_all(students)
        self.db.flush()
        return students
