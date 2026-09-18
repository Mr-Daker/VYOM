with open("app/services/grouping_service.py", "r") as f:
    content = f.read()

old_is_usable = """                is_usable = (
                    snap is not None and 
                    snap.source != "none" and 
                    not snap.stale and 
                    snap.score is not None and
                    snap.state is not None
                )"""

new_is_usable = """                is_usable = (
                    snap is not None and 
                    snap.source != "none" and 
                    not snap.stale and 
                    snap.score is not None and
                    snap.state is not None and
                    snap.state != MasteryState.UNKNOWN
                )"""
content = content.replace(old_is_usable, new_is_usable)

old_persistence = """                db_g = LearningGroup(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    name=name,
                    group_type=cg.group_type,
                    focus_competency_id=cg.focus_comp.id if cg.focus_comp else None,
                    check_mode=cg.check_mode,
                    reason=reason,
                    mixed_needs=cg.mixed_needs,
                    sort_order=idx
                )
                self.db.add(db_g)
                db_groups.append(db_g)
                
                for m in cg.members:
                    db_m = GroupMembership(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        group_id=db_g.id,
                        student_id=m.student.id,
                        focus_competency_id=m.focus_comp.id if m.focus_comp else None,
                        assignment_reason=m.assignment_reason,
                        original_group_type=m.original_group_type,
                        original_check_mode=m.original_check_mode
                    )
                    self.db.add(db_m)"""

new_persistence = """                db_g = LearningGroup(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    name=name,
                    group_type=cg.group_type,
                    focus_competency_id=cg.focus_comp.id if cg.focus_comp else None,
                    check_mode=cg.check_mode,
                    reason=reason,
                    mixed_needs=cg.mixed_needs,
                    sort_order=idx
                )
                self.db.add(db_g)
                self.db.flush()
                db_groups.append(db_g)
                
                for m in cg.members:
                    db_m = GroupMembership(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        group_id=db_g.id,
                        student_id=m.student.id,
                        focus_competency_id=m.focus_comp.id if m.focus_comp else None,
                        assignment_reason=m.assignment_reason,
                        original_group_type=m.original_group_type,
                        original_check_mode=m.original_check_mode
                    )
                    self.db.add(db_m)
                    self.db.flush()"""
content = content.replace(old_persistence, new_persistence)

with open("app/services/grouping_service.py", "w") as f:
    f.write(content)
