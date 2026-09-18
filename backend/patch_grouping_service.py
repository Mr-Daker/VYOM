with open("app/services/grouping_service.py", "r") as f:
    content = f.read()

# Update regenerate block to clear priority
old_clear = """            self.mem_repo.delete_for_session(session_id)
            self.group_repo.delete_for_session(session_id)"""
new_clear = """            from app.repositories.priority_repository import GroupPriorityRepository
            GroupPriorityRepository(self.db).delete_for_session(session_id)
            session.priority_generated_at = None
            session.priority_stale = False
            self.mem_repo.delete_for_session(session_id)
            self.group_repo.delete_for_session(session_id)"""
content = content.replace(old_clear, new_clear)

# Update move_student to set priority_stale
old_move_try = """        try:
            mem.group_id = target_group.id
            if req.reason:
                mem.teacher_override_reason = req.reason
                
            target_group.teacher_modified = True
            source_group.teacher_modified = True
            session.groups_teacher_modified = True"""
new_move_try = """        try:
            mem.group_id = target_group.id
            if req.reason:
                mem.teacher_override_reason = req.reason
                
            target_group.teacher_modified = True
            source_group.teacher_modified = True
            session.groups_teacher_modified = True
            if session.priority_generated_at is not None:
                session.priority_stale = True"""
content = content.replace(old_move_try, new_move_try)

# Update update_group to set priority_stale
old_update_try = """        try:
            if req.name is not None:
                target_group.name = req.name
            if req.reason is not None:
                target_group.reason = req.reason
            target_group.teacher_modified = True
            session.groups_teacher_modified = True"""
new_update_try = """        try:
            if req.name is not None:
                target_group.name = req.name
            if req.reason is not None:
                target_group.reason = req.reason
            target_group.teacher_modified = True
            session.groups_teacher_modified = True
            if session.priority_generated_at is not None:
                session.priority_stale = True"""
content = content.replace(old_update_try, new_update_try)

with open("app/services/grouping_service.py", "w") as f:
    f.write(content)
