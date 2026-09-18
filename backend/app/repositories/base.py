from sqlalchemy.orm import Session
from uuid import UUID

class BaseRepository:
    def __init__(self, db: Session):
        self.db = db
