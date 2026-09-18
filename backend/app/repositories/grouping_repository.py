from typing import List
from uuid import UUID
from app.repositories.base import BaseRepository
from app.models.all_models import LearningGroup, GroupMembership

class LearningGroupRepository(BaseRepository):
    def get_by_session(self, session_id: UUID) -> List[LearningGroup]:
        return self.db.query(LearningGroup).filter(LearningGroup.session_id == session_id).order_by(LearningGroup.sort_order).all()

    def get_with_members(self, session_id: UUID) -> List[LearningGroup]:
        return self.db.query(LearningGroup).filter(LearningGroup.session_id == session_id).order_by(LearningGroup.sort_order).all()

    def delete_for_session(self, session_id: UUID):
        self.db.query(LearningGroup).filter(LearningGroup.session_id == session_id).delete()
        self.db.flush()

    def has_teacher_modifications(self, session_id: UUID) -> bool:
        mod = self.db.query(LearningGroup).filter(
            LearningGroup.session_id == session_id,
            LearningGroup.teacher_modified == True
        ).first()
        return bool(mod)

    def get_by_id(self, group_id: UUID) -> LearningGroup:
        return self.db.query(LearningGroup).filter(LearningGroup.id == group_id).first()


class GroupMembershipRepository(BaseRepository):
    def get_by_session(self, session_id: UUID) -> List[GroupMembership]:
        return self.db.query(GroupMembership).filter(GroupMembership.session_id == session_id).all()

    def delete_for_session(self, session_id: UUID):
        self.db.query(GroupMembership).filter(GroupMembership.session_id == session_id).delete()
        self.db.flush()
        
    def get_membership(self, session_id: UUID, student_id: UUID) -> GroupMembership:
        return self.db.query(GroupMembership).filter(
            GroupMembership.session_id == session_id, 
            GroupMembership.student_id == student_id
        ).first()
