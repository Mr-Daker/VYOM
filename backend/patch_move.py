import re

with open("app/services/grouping_service.py", "r") as f:
    content = f.read()

# Add normalize helper
if "def normalize_group_sort_order(self, session_id: UUID):" not in content:
    normalize_helper = """    def normalize_group_sort_order(self, session_id: UUID):
        groups = self.group_repo.get_by_session(session_id)
        # stable sort by current sort_order, then ID
        groups.sort(key=lambda g: (g.sort_order, str(g.id)))
        for idx, g in enumerate(groups):
            g.sort_order = idx

    def move_student"""
    content = content.replace("    def move_student", normalize_helper)

# Replace move_student try block
old_move_try = """        try:
            mem.group_id = target_group.id
            if req.reason:
                mem.teacher_override_reason = req.reason
            session.groups_teacher_modified = True
            
            self.db.flush()
            
            source_mems = self.db.query(GroupMembership).filter(GroupMembership.group_id == source_group.id).count()
            if source_mems == 0:
                self.db.delete(source_group)
                
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise AppException("GROUPING_FAILED", str(e), 500)"""

new_move_try = """        try:
            mem.group_id = target_group.id
            if req.reason:
                mem.teacher_override_reason = req.reason
                
            target_group.teacher_modified = True
            source_group.teacher_modified = True
            session.groups_teacher_modified = True
            
            self.db.flush()
            
            source_mems = self.db.query(GroupMembership).filter(GroupMembership.group_id == source_group.id).count()
            if source_mems == 0:
                self.db.delete(source_group)
                self.db.flush()
                self.normalize_group_sort_order(session_id)
                
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise AppException("GROUPING_FAILED", str(e), 500)"""

content = content.replace(old_move_try, new_move_try)

with open("app/services/grouping_service.py", "w") as f:
    f.write(content)
