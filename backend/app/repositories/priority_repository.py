from typing import List, Optional
from uuid import UUID
from app.repositories.base import BaseRepository
from app.models.all_models import GroupPriority

class GroupPriorityRepository(BaseRepository):
    def get_by_session(self, session_id: UUID) -> List[GroupPriority]:
        return self.db.query(GroupPriority).filter(GroupPriority.session_id == session_id).order_by(GroupPriority.priority_rank).all()
        
    def get_by_group(self, group_id: UUID) -> Optional[GroupPriority]:
        return self.db.query(GroupPriority).filter(GroupPriority.group_id == group_id).first()
        
    def delete_for_session(self, session_id: UUID):
        self.db.query(GroupPriority).filter(GroupPriority.session_id == session_id).delete()
        self.db.flush()
        
    def has_teacher_override(self, session_id: UUID) -> bool:
        overridden = self.db.query(GroupPriority).filter(
            GroupPriority.session_id == session_id,
            GroupPriority.teacher_rank.isnot(None)
        ).first()
        return bool(overridden)
