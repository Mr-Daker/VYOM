from typing import List, Dict, Optional
from uuid import UUID
import uuid

from app.services.base import BaseService
from app.services.gap_detection_service import GapDetectionService
from app.services.mastery_snapshot_service import MasterySnapshotService
from app.repositories.session_repository import SessionRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.competency_repository import CompetencyRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.grouping_repository import LearningGroupRepository, GroupMembershipRepository
from app.models.all_models import LearningGroup, GroupMembership
from app.models.enums import SessionStatus, AttendanceStatus, GroupType, CheckMode, GapClassification, OverallReadinessStatus, MasteryState
from app.schemas.grouping import GroupingResponse, LearningGroupResponse, GroupMemberResponse, ExcludedStudentResponse, GroupingSummary, CompetencyRef
from app.core.exceptions import AppException

class CandidateMember:
    def __init__(self, student, assessment, focus_comp, reason, original_group_type, original_check_mode):
        self.student = student
        self.assessment = assessment
        self.focus_comp = focus_comp
        self.assignment_reason = reason
        self.original_group_type = original_group_type
        self.original_check_mode = original_check_mode

class CandidateGroup:
    def __init__(self, group_type: GroupType, focus_comp=None, check_mode=None):
        self.group_type = group_type
        self.focus_comp = focus_comp
        self.check_mode = check_mode
        self.members: List[CandidateMember] = []
        self.mixed_needs = False

class GroupingService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.session_repo = SessionRepository(db)
        self.student_repo = StudentRepository(db)
        self.comp_repo = CompetencyRepository(db)
        self.att_repo = AttendanceRepository(db)
        self.group_repo = LearningGroupRepository(db)
        self.mem_repo = GroupMembershipRepository(db)
        self.gap_service = GapDetectionService(db)
        self.snapshot_service = MasterySnapshotService(db)

    def generate_groups(self, session_id: UUID, replace_existing: bool = False, force_replace_teacher_edits: bool = False):
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise AppException("NOT_FOUND", "Session not found", 404)
        
        if session.status not in [SessionStatus.DRAFT, SessionStatus.ATTENDANCE_RECORDED, SessionStatus.GROUPED]:
            raise AppException("VALIDATION_ERROR", f"Cannot group session in status {session.status}", 400)
            
        existing_groups = self.group_repo.get_by_session(session_id)
        if existing_groups:
            if not replace_existing:
                raise AppException("CONFLICT", "Groups already exist for this session.", 409)
            if session.groups_teacher_modified and not force_replace_teacher_edits:
                raise AppException("CONFLICT", "Existing groups contain manual teacher edits. Must force replace.", 409)

        classroom_id = session.classroom_id
        classroom = session.classroom
        students = self.student_repo.get_by_classroom(classroom_id)
        active_students = [s for s in students if s.active]
        
        att_records = self.att_repo.get_by_session(session_id)
        current_atts = {a.student_id: a.status for a in att_records}
        for s in active_students:
            if s.id not in current_atts:
                raise AppException("ATTENDANCE_INCOMPLETE", "Not all active students have attendance recorded.", 409)

        gap_response = self.gap_service.detect_gaps(session_id)
        
        target_comp = None
        if session.target_competency_id:
            target_comp = self.comp_repo.get_by_id(session.target_competency_id)
            
        all_comps = {c.id: c for c in self.comp_repo.get_all()}
        
        target_snaps = {}
        if target_comp:
            target_snaps = self.snapshot_service.resolve_bulk([s.id for s in active_students], [target_comp.id], session.date)

        excluded = []
        eligible_students = []
        
        for s_ast in gap_response.students:
            s_obj = next(s for s in active_students if s.id == s_ast.student_id)
            if s_ast.current_attendance == AttendanceStatus.ABSENT:
                excluded.append((s_obj, "absent"))
            else:
                eligible_students.append((s_obj, s_ast))
                
        candidate_groups: List[CandidateGroup] = []
        
        def get_or_create_group(g_type, f_comp, check_mode=None) -> CandidateGroup:
            for cg in candidate_groups:
                if cg.group_type == g_type and cg.focus_comp == f_comp and cg.check_mode == check_mode:
                    return cg
            cg = CandidateGroup(g_type, f_comp, check_mode)
            candidate_groups.append(cg)
            return cg
            
        def determine_primary_gap(s_ast):
            prereqs = s_ast.direct_prerequisites
            if not prereqs: return None
            
            def severity(cls):
                if cls == GapClassification.CONFIRMED_GAP: return 5
                if cls == GapClassification.LIKELY_GAP: return 4
                if cls == GapClassification.INSUFFICIENT_EVIDENCE: return 3
                if cls == GapClassification.DEVELOPING: return 2
                return 1
                
            sorted_prereqs = sorted(prereqs, key=lambda p: (
                -severity(p.classification),
                p.mastery_score if p.mastery_score is not None else 999.0,
                p.competency_code
            ))
            return sorted_prereqs[0]

        for s_obj, s_ast in eligible_students:
            overall = s_ast.overall_status
            
            if overall == OverallReadinessStatus.NEEDS_SUPPORT:
                primary = determine_primary_gap(s_ast)
                f_comp = all_comps[primary.competency_id]
                reason = f"{f_comp.name} is a prerequisite for {target_comp.name if target_comp else 'the target'}; current classification is {primary.classification.value.replace('_', ' ')}."
                if primary.classification == GapClassification.LIKELY_GAP and primary.absent_sessions > 0:
                     reason = f"{f_comp.name} is a prerequisite for {target_comp.name if target_comp else 'the target'}; current mastery is developing and student missed {primary.absent_sessions} prerequisite session(s)."
                cg = get_or_create_group(GroupType.RECOVERY, f_comp)
                cg.members.append(CandidateMember(s_obj, s_ast, f_comp, reason, GroupType.RECOVERY.value, None))
                
            elif overall == OverallReadinessStatus.NEEDS_CHECK:
                primary = determine_primary_gap(s_ast)
                f_comp = all_comps[primary.competency_id]
                c_mode = CheckMode.ASSESSMENT if primary.classification == GapClassification.INSUFFICIENT_EVIDENCE else CheckMode.QUICK_CHECK
                reason = f"Requires {c_mode.value.replace('_', ' ')} for prerequisite {f_comp.name} before proceeding."
                cg = get_or_create_group(GroupType.CHECK, f_comp, check_mode=c_mode)
                cg.members.append(CandidateMember(s_obj, s_ast, f_comp, reason, GroupType.CHECK.value, c_mode.value))
                
            else:
                # READY or NO_PREREQUISITES
                snap = target_snaps.get((s_obj.id, target_comp.id)) if target_comp else None
                
                # Usable target evidence requires: snap exists, source != "none", not stale, score is not None
                is_usable = (
                    snap is not None and 
                    snap.source != "none" and 
                    not snap.stale and 
                    snap.score is not None and
                    snap.state is not None and
                    snap.state != MasteryState.UNKNOWN
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
                    cg.members.append(CandidateMember(s_obj, s_ast, target_comp, reason, GroupType.EXTENSION.value, None))

        max_g = classroom.max_groups
        warnings = []
        compressed = False
        
        # Sort members deterministically
        for cg in candidate_groups:
            cg.members.sort(key=lambda m: str(m.student.id))
            
        # Deterministic order before compression
        def type_order(gt):
            order = {GroupType.RECOVERY: 1, GroupType.CHECK: 2, GroupType.GUIDED: 3, GroupType.PRACTICE: 4, GroupType.EXTENSION: 5, GroupType.MIXED_SUPPORT: 6}
            return order.get(gt, 99)
            
        candidate_groups.sort(key=lambda g: (type_order(g.group_type), g.focus_comp.code if g.focus_comp else "", g.check_mode.value if g.check_mode else ""))
        candidate_groups = [cg for cg in candidate_groups if len(cg.members) > 0]
        
        # Rule 1: Practice + Extension -> Practice
        if len(candidate_groups) > max_g:
            pr_idx = next((i for i, g in enumerate(candidate_groups) if g.group_type == GroupType.PRACTICE), -1)
            ex_idx = next((i for i, g in enumerate(candidate_groups) if g.group_type == GroupType.EXTENSION), -1)
            if pr_idx != -1 and ex_idx != -1:
                pr_group = candidate_groups[pr_idx]
                ex_group = candidate_groups[ex_idx]
                for m in ex_group.members:
                    pr_group.members.append(m)
                pr_group.mixed_needs = True
                del candidate_groups[ex_idx]
                compressed = True
                warnings.append("Practice and extension learners were combined to respect the classroom limit.")
                
        # Rule 2: Guided + Practice -> Guided
        if len(candidate_groups) > max_g:
            gu_idx = next((i for i, g in enumerate(candidate_groups) if g.group_type == GroupType.GUIDED), -1)
            pr_idx = next((i for i, g in enumerate(candidate_groups) if g.group_type == GroupType.PRACTICE), -1)
            if gu_idx != -1 and pr_idx != -1:
                gu_group = candidate_groups[gu_idx]
                pr_group = candidate_groups[pr_idx]
                for m in pr_group.members:
                    gu_group.members.append(m)
                gu_group.mixed_needs = True
                pr_idx = candidate_groups.index(pr_group)
                del candidate_groups[pr_idx]
                compressed = True
                warnings.append("Guided and practice learners were combined to respect the classroom limit.")
                
        # Rule 3: Check + Recovery (same focus) -> Recovery
        if len(candidate_groups) > max_g:
            i = 0
            while len(candidate_groups) > max_g and i < len(candidate_groups):
                g = candidate_groups[i]
                if g.group_type == GroupType.CHECK:
                    rec_idx = next((j for j, rg in enumerate(candidate_groups) if rg.group_type == GroupType.RECOVERY and rg.focus_comp == g.focus_comp), -1)
                    if rec_idx != -1:
                        rec_group = candidate_groups[rec_idx]
                        for m in g.members:
                            rec_group.members.append(m)
                        rec_group.mixed_needs = True
                        candidate_groups.pop(i)
                        compressed = True
                        warnings.append(f"Check and recovery for {g.focus_comp.name} were combined to respect the classroom limit.")
                        continue
                i += 1
                
        # Rule 4: Mixed Support Fallback
        if len(candidate_groups) > max_g:
            support_groups = [g for g in candidate_groups if g.group_type in [GroupType.RECOVERY, GroupType.CHECK]]
            if len(support_groups) > 1:
                support_groups.sort(key=lambda x: (len(x.members), type_order(x.group_type), x.focus_comp.code if x.focus_comp else ""))
                
                mixed_group = get_or_create_group(GroupType.MIXED_SUPPORT, None)
                mixed_group.mixed_needs = True
                
                while len(candidate_groups) > max_g and support_groups:
                    smallest = support_groups.pop(0)
                    for m in smallest.members:
                        mixed_group.members.append(m)
                    if smallest in candidate_groups:
                        candidate_groups.remove(smallest)
                        
                if mixed_group.members and mixed_group not in candidate_groups:
                    candidate_groups.append(mixed_group)
                if len(mixed_group.members) > 0:
                    compressed = True
                    warnings.append("Multiple prerequisite needs were combined because the classroom permits limited simultaneous groups.")

        # Re-sort remaining to normalize
        for cg in candidate_groups: cg.members.sort(key=lambda m: str(m.student.id))
        candidate_groups = [cg for cg in candidate_groups if len(cg.members) > 0]
        candidate_groups.sort(key=lambda g: (type_order(g.group_type), g.focus_comp.code if g.focus_comp else "", g.check_mode.value if g.check_mode else ""))

        if len(candidate_groups) > max_g:
            raise AppException("GROUP_CAPACITY_UNSATISFIABLE", "The configured maximum group count cannot represent the current learning needs without combining prerequisite-support students with incompatible target-level groups.", 409)

        all_assigned = sum(len(g.members) for g in candidate_groups)
        if all_assigned != len(eligible_students):
            raise AppException("GROUPING_FAILED", "Not all eligible students assigned correctly.", 500)

        try:
            from app.repositories.priority_repository import GroupPriorityRepository
            GroupPriorityRepository(self.db).delete_for_session(session_id)
            pass
            pass
            self.mem_repo.delete_for_session(session_id)
            self.group_repo.delete_for_session(session_id)
            
            db_groups = []
            
            for idx, cg in enumerate(candidate_groups):
                name = cg.group_type.value.capitalize()
                if cg.focus_comp:
                    name += f" — {cg.focus_comp.name}"
                if cg.group_type == GroupType.MIXED_SUPPORT:
                    name = "Mixed Support"
                    
                reason = "These students "
                if cg.group_type == GroupType.RECOVERY: reason += f"currently need support with {cg.focus_comp.name} before continuing."
                elif cg.group_type == GroupType.CHECK: reason += f"need a readiness check for {cg.focus_comp.name}."
                elif cg.group_type == GroupType.GUIDED: reason += "are ready to begin guided instruction."
                elif cg.group_type == GroupType.PRACTICE: reason += "have the required prerequisites and are developing the target."
                elif cg.group_type == GroupType.EXTENSION: reason += "have demonstrated current mastery of the target and can work on extension tasks."
                else: reason += "have mixed prerequisite support needs."
                
                db_g = LearningGroup(
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
                    self.db.flush()
                    
            session.status = SessionStatus.GROUPED
            session.grouping_warnings = warnings
            session.grouping_compressed = compressed
            session.groups_teacher_modified = False
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise AppException("GROUPING_FAILED", str(e), 500)
            
        return self.get_groups(session_id)

    def get_groups(self, session_id: UUID):
        session = self.session_repo.get_by_id(session_id)
        if not session: raise AppException("NOT_FOUND", "Session not found", 404)
        
        db_groups = self.group_repo.get_by_session(session_id)
        memberships = self.mem_repo.get_by_session(session_id)
        students = self.student_repo.get_by_classroom(session.classroom_id)
        students_dict = {s.id: s for s in students}
        
        att_records = self.att_repo.get_by_session(session_id)
        att_dict = {a.student_id: a for a in att_records}
        
        grouped_student_ids = {m.student_id for m in memberships}
        active_students = [s for s in students if s.active]
        excluded = []
        for s in active_students:
            if s.id not in grouped_student_ids:
                att = att_dict.get(s.id)
                r = "absent" if (att and att.status == AttendanceStatus.ABSENT) else "attendance_unknown"
                excluded.append(ExcludedStudentResponse(student_id=s.id, name=s.name, reason=r))
                
        all_comps = {c.id: c for c in self.comp_repo.get_all()}
        target_comp = all_comps.get(session.target_competency_id) if session.target_competency_id else None
        
        target_snaps = {}
        if target_comp:
            target_snaps = self.snapshot_service.resolve_bulk([s.id for s in active_students], [target_comp.id], session.date)
        
        out_groups = []
        for g in db_groups:
            g_mems = [m for m in memberships if m.group_id == g.id]
            st_out = []
            g_dist = {}
            l_dist = {}
            for m in g_mems:
                s = students_dict[m.student_id]
                
                t_score, t_state, t_source, t_stale = None, None, None, None
                if target_comp:
                    snap = target_snaps.get((s.id, target_comp.id))
                    if snap:
                        t_score = snap.score
                        t_state = snap.state.value if snap.state else None
                        t_source = snap.source
                        t_stale = snap.stale
                
                st_out.append(GroupMemberResponse(
                    student_id=s.id, name=s.name, grade=s.grade,
                    preferred_language=s.preferred_language,
                    focus_competency_id=m.focus_competency_id,
                    assignment_reason=m.assignment_reason,
                    original_group_type=m.original_group_type,
                    original_check_mode=m.original_check_mode,
                    teacher_override_reason=m.teacher_override_reason,
                    target_mastery_score=t_score,
                    target_mastery_state=t_state,
                    target_mastery_source=t_source,
                    target_mastery_stale=t_stale
                ))
                g_dist[str(s.grade)] = g_dist.get(str(s.grade), 0) + 1
                lang = s.preferred_language or "Unknown"
                l_dist[lang] = l_dist.get(lang, 0) + 1
                
            f_ref = None
            if g.focus_competency_id:
                fc = all_comps[g.focus_competency_id]
                f_ref = CompetencyRef(id=fc.id, code=fc.code, name=fc.name)
                
            out_groups.append(LearningGroupResponse(
                id=g.id, name=g.name, group_type=g.group_type.value,
                check_mode=g.check_mode.value if g.check_mode else None,
                focus_competency=f_ref, student_count=len(st_out),
                mixed_needs=g.mixed_needs, grade_distribution=g_dist,
                language_distribution=l_dist, reason=g.reason,
                students=st_out
            ))
            
        t_ref = None
        if target_comp:
            t_ref = CompetencyRef(id=target_comp.id, code=target_comp.code, name=target_comp.name)
            
        summ = GroupingSummary(
            active_students=len(active_students),
            eligible_students=len(grouped_student_ids),
            absent_students=len([e for e in excluded if e.reason == "absent"]),
            groups_created=len(out_groups),
            max_groups=session.classroom.max_groups,
            compressed=session.grouping_compressed
        )
        
        return GroupingResponse(
            session_id=session_id, target_competency=t_ref,
            summary=summ, groups=out_groups, excluded_students=excluded, warnings=session.grouping_warnings or []
        )

    def normalize_group_sort_order(self, session_id: UUID):
        groups = self.group_repo.get_by_session(session_id)
        # stable sort by current sort_order, then ID
        groups.sort(key=lambda g: (g.sort_order, str(g.id)))
        for idx, g in enumerate(groups):
            g.sort_order = idx

    def move_student(self, session_id: UUID, req):
        session = self.session_repo.get_by_id(session_id)
        if not session: raise AppException("NOT_FOUND", "Session not found", 404)
        
        if session.status != SessionStatus.GROUPED:
            raise AppException("INVALID_SESSION_STATE", f"Cannot move students when session status is {session.status}", 400)
            
        student = self.student_repo.get_by_id(req.student_id)
        if not student or student.classroom_id != session.classroom_id or not student.active:
            raise AppException("VALIDATION_ERROR", "Invalid, inactive, or mismatched student", 400)
            
        att = self.att_repo.get_by_student_and_session(req.student_id, session_id)
        if not att: raise AppException("ATTENDANCE_INCOMPLETE", "Missing attendance for student", 409)
        if att.status == AttendanceStatus.ABSENT:
            raise AppException("VALIDATION_ERROR", "Cannot move an absent student", 400)
            
        mem = self.mem_repo.get_membership(session_id, req.student_id)
        if not mem: raise AppException("VALIDATION_ERROR", "Student not found in session groups", 400)
        
        if mem.group_id == req.target_group_id:
            return self.get_groups(session_id)
            
        target_group = self.group_repo.get_by_id(req.target_group_id)
        if not target_group or target_group.session_id != session_id:
            raise AppException("VALIDATION_ERROR", "Target group invalid", 400)
            
        source_group = self.group_repo.get_by_id(mem.group_id)
        
        try:
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
            raise AppException("GROUPING_FAILED", str(e), 500)
            
        return self.get_groups(session_id)
        
    def update_group(self, session_id: UUID, group_id: UUID, req):
        session = self.session_repo.get_by_id(session_id)
        if not session: raise AppException("NOT_FOUND", "Session not found", 404)
        
        if session.status != SessionStatus.GROUPED:
            raise AppException("INVALID_SESSION_STATE", f"Cannot update groups when session status is {session.status}", 400)
            
        target_group = self.group_repo.get_by_id(group_id)
        if not target_group or target_group.session_id != session_id:
            raise AppException("VALIDATION_ERROR", "Target group invalid", 400)
            
        try:
            if req.name is not None:
                target_group.name = req.name
            if req.reason is not None:
                target_group.reason = req.reason
            target_group.teacher_modified = True
            session.groups_teacher_modified = True
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise AppException("GROUPING_FAILED", str(e), 500)
            
        return self.get_groups(session_id)

