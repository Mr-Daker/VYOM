import re

with open("app/services/grouping_service.py", "r") as f:
    content = f.read()

old_update_try = """        try:
            if req.name is not None:
                target_group.name = req.name
            if req.reason is not None:
                target_group.reason = req.reason
            session.groups_teacher_modified = True
            self.db.commit()"""

new_update_try = """        try:
            if req.name is not None:
                target_group.name = req.name
            if req.reason is not None:
                target_group.reason = req.reason
            target_group.teacher_modified = True
            session.groups_teacher_modified = True
            self.db.commit()"""

content = content.replace(old_update_try, new_update_try)

with open("app/services/grouping_service.py", "w") as f:
    f.write(content)
