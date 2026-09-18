from app.repositories.base import BaseRepository
from app.models.all_models import Classroom
from uuid import UUID

class ClassroomRepository(BaseRepository):
    def get_by_id(self, classroom_id: UUID) -> Classroom | None:
        return self.db.query(Classroom).filter(Classroom.id == classroom_id).first()
        
    def get_all(self):
        return self.db.query(Classroom).all()
        
    def add(self, classroom: Classroom):
        self.db.add(classroom)
        self.db.flush()
        return classroom
