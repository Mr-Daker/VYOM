from app.repositories.base import BaseRepository
from app.models.all_models import User
from uuid import UUID

class UserRepository(BaseRepository):
    def get_by_id(self, user_id: UUID) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()
        
    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()
        
    def add(self, user: User):
        self.db.add(user)
        self.db.flush()
        return user
