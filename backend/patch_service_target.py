import re

with open("app/services/grouping_service.py", "r") as f:
    content = f.read()

# Replace the target mastery logic block
old_target_logic = """                # READY or NO_PREREQUISITES
                snap = target_snaps.get((s_obj.id, target_comp.id)) if target_comp else None
                score = snap.score if snap else None
                
                if score is None or score < 0.40:
                    reason = "Ready to begin guided instruction on the target competency."
                    cg = get_or_create_group(GroupType.GUIDED, target_comp)
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.GUIDED.value, None))
                elif score < 0.70:
                    reason = "Prerequisites are ready and current target mastery is developing. Needs practice."
                    cg = get_or_create_group(GroupType.PRACTICE, target_comp)
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.PRACTICE.value, None))
                else:
                    reason = "Demonstrated mastery of the target competency. Ready for extension."
                    cg = get_or_create_group(GroupType.EXTENSION, target_comp)
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.EXTENSION.value, None))"""

new_target_logic = """                # READY or NO_PREREQUISITES
                snap = target_snaps.get((s_obj.id, target_comp.id)) if target_comp else None
                
                # Usable target evidence requires: snap exists, source != "none", not stale, score is not None
                is_usable = (
                    snap is not None and 
                    snap.source != "none" and 
                    not snap.stale and 
                    snap.score is not None and
                    snap.state is not None
                )
                
                if not is_usable or snap.score < 0.40:
                    reason = "Ready to begin guided instruction on the target competency."
                    cg = get_or_create_group(GroupType.GUIDED, target_comp)
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.GUIDED.value, None))
                elif snap.score < 0.70:
                    reason = "Prerequisites are ready and current target mastery is developing. Needs practice."
                    cg = get_or_create_group(GroupType.PRACTICE, target_comp)
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.PRACTICE.value, None))
                else:
                    reason = "Demonstrated mastery of the target competency. Ready for extension."
                    cg = get_or_create_group(GroupType.EXTENSION, target_comp)
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.EXTENSION.value, None))"""

content = content.replace(old_target_logic, new_target_logic)

with open("app/services/grouping_service.py", "w") as f:
    f.write(content)
