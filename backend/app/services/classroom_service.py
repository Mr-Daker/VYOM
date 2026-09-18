from app.services.base import BaseService
from app.repositories.classroom_repository import ClassroomRepository
from app.repositories.user_repository import UserRepository
from app.models.all_models import Classroom
from app.schemas.classroom import ClassroomCreate, ClassroomUpdate
from app.core.exceptions import AppException
from uuid import UUID

class ClassroomService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.class_repo = ClassroomRepository(db)
        self.user_repo = UserRepository(db)

    def create_classroom(self, schema: ClassroomCreate):
        u = self.user_repo.get_by_id(schema.teacher_id)
        if not u:
            raise AppException("NOT_FOUND", "Teacher not found", 404)
        c = Classroom(**schema.model_dump())
        try:
            self.class_repo.add(c)
            self.db.commit()
            self.db.refresh(c)
            return c
        except Exception as e:
            self.db.rollback()
            raise e

    def get_classrooms(self):
        return self.class_repo.get_all()

    def get_classroom(self, classroom_id: UUID):
        c = self.class_repo.get_by_id(classroom_id)
        if not c:
            raise AppException("NOT_FOUND", "Classroom not found", 404)
        return c

    def update_classroom(self, classroom_id: UUID, schema: ClassroomUpdate):
        c = self.get_classroom(classroom_id)
        try:
            for k, v in schema.model_dump(exclude_unset=True).items():
                setattr(c, k, v)
            self.db.commit()
            self.db.refresh(c)
            return c
        except Exception as e:
            self.db.rollback()
            raise e
