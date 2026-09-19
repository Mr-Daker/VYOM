from typing import List, Dict, Optional, Tuple
from uuid import UUID
import uuid
from datetime import datetime, timezone

from app.services.base import BaseService
from app.services.gap_detection_service import GapDetectionService
from app.services.mastery_snapshot_service import MasterySnapshotService
from app.repositories.session_repository import SessionRepository
from app.repositories.grouping_repository import LearningGroupRepository, GroupMembershipRepository
from app.repositories.priority_repository import GroupPriorityRepository
from app.models.all_models import GroupPriority, LearningGroup, GroupMembership
from app.models.enums import SessionStatus, GroupType, CheckMode, GapClassification, OverallReadinessStatus, MasteryState
from app.schemas.priority import (
    SessionPriorityResponse, GroupPriorityResponse, PriorityFactors, FactorBreakdown, PrioritySummary
)
from app.core.exceptions import AppException
from app.core.priority_config import (
    validate_priority_config, get_tier_for_score, PRIORITY_WEIGHTS, INSTRUCTIONAL_NEED_VALUES, 
    PREREQUISITE_SEVERITY_VALUES, TARGET_SEVERITY_VALUES, UNCERTAINTY_VALUES, COMPLEXITY_VALUES, 
    PRIORITY_REFERENCE_GROUP_SIZE, FACTOR_ORDER
)

def select_top_factor(contributions: Dict[str, float]) -> Optional[str]:
    """Helper to deterministically select the top reason tie-breaker based on highest contribution."""
    factors_list = list(contributions.items())
    # Sort by contribution (descending), then by index in FACTOR_ORDER (ascending to prefer earlier items)
    factors_list.sort(key=lambda f: (-f[1], FACTOR_ORDER.index(f[0])))
    
    if not factors_list or factors_list[0][1] <= 0: return None
    return factors_list[0][0]
    return top_reason_key

class TeacherPriorityService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        validate_priority_config()
            
        self.session_repo = SessionRepository(db)
        self.group_repo = LearningGroupRepository(db)
        self.mem_repo = GroupMembershipRepository(db)
        self.priority_repo = GroupPriorityRepository(db)
        self.gap_service = GapDetectionService(db)
        self.snapshot_service = MasterySnapshotService(db)
        
    def generate_priorities(self, session_id: UUID, req) -> SessionPriorityResponse:
        session = self.session_repo.get_by_id(session_id)
        if not session: raise AppException("NOT_FOUND", "Session not found", 404)
        
        if session.status != SessionStatus.GROUPED:
            raise AppException("INVALID_SESSION_STATE", f"Cannot generate priority for status {session.status}", 400)
            
        groups = self.group_repo.get_by_session(session_id)
        if not groups:
            raise AppException("NO_GROUPS", "Cannot generate priority. No groups found.", 400)
            
        existing_priorities = self.priority_repo.get_by_session(session_id)
        if existing_priorities:
            if not req.replace_existing:
                raise AppException("CONFLICT", "Priorities already exist.", 409)
            if self.priority_repo.has_teacher_override(session_id) and not req.force_replace_teacher_priority:
                raise AppException("CONFLICT", "Existing priorities contain manual teacher edits. Must force replace.", 409)

        memberships = self.mem_repo.get_by_session(session_id)
        
        for g in groups:
            if not any(m.group_id == g.id for m in memberships):
                raise AppException("PRIORITY_INVALID_GROUPING", "Empty groups found in session. Priority generation rejected.", 409)
        
        gap_response = self.gap_service.detect_gaps(session_id)
        gap_dict = {s.student_id: s for s in gap_response.students}
        
        target_snaps = {}
        if session.target_competency_id:
            student_ids = [m.student_id for m in memberships]
            target_snaps = self.snapshot_service.resolve_bulk(student_ids, [session.target_competency_id], session.date)
            
        calculated_groups = []
        
        for g in groups:
            g_mems = [m for m in memberships if m.group_id == g.id]
            
            reasons = []
            def add_reason(r):
                if r not in reasons: reasons.append(r)
            
            needs = [INSTRUCTIONAL_NEED_VALUES.get(m.original_group_type, 0.0) for m in g_mems]
            avg_need = sum(needs) / len(needs)
            
            rec_count = sum(1 for n in needs if n == INSTRUCTIONAL_NEED_VALUES["recovery"])
            if rec_count > 0:
                add_reason(f"{rec_count} of {len(needs)} learners currently require prerequisite recovery.")
            
            severities = []
            missed_ratios = []
            uncertainties = []
            
            confirmed_gap_count = 0
            assess_req_count = 0
            missed_sess_sum = 0
            missed_sess_rel = 0
            missing_gap_evidence = 0
            
            for m in g_mems:
                ast = gap_dict.get(m.student_id)
                snap = target_snaps.get((m.student_id, session.target_competency_id))
                
                if m.original_group_type in [GroupType.RECOVERY.value, GroupType.CHECK.value]:
                    prereqs = ast.direct_prerequisites if ast else None
                    match_p = next((p for p in prereqs if p.competency_id == m.focus_competency_id), None) if prereqs else None
                    if match_p:
                        c_val = 0.0
                        cls = match_p.classification
                        if cls == GapClassification.CONFIRMED_GAP: 
                            c_val = PREREQUISITE_SEVERITY_VALUES["confirmed_gap"]
                            confirmed_gap_count += 1
                        elif cls == GapClassification.LIKELY_GAP: c_val = PREREQUISITE_SEVERITY_VALUES["likely_gap"]
                        elif cls == GapClassification.INSUFFICIENT_EVIDENCE: c_val = PREREQUISITE_SEVERITY_VALUES["insufficient_evidence"]
                        elif cls == GapClassification.DEVELOPING: c_val = PREREQUISITE_SEVERITY_VALUES["developing"]
                        elif cls == GapClassification.READY: c_val = PREREQUISITE_SEVERITY_VALUES["ready"]
                        severities.append(c_val)
                        
                        if match_p.relevant_sessions > 0:
                            rat = match_p.absent_sessions / match_p.relevant_sessions
                            missed_ratios.append(min(max(rat, 0.0), 1.0))
                            missed_sess_sum += match_p.absent_sessions
                            missed_sess_rel += match_p.relevant_sessions
                        else:
                            missed_ratios.append(0.0)
                    else:
                        missing_gap_evidence += 1
                        severities.append(0.0)
                        missed_ratios.append(0.0)
                        
                    if m.original_group_type == GroupType.CHECK.value:
                        if m.original_check_mode == CheckMode.ASSESSMENT.value:
                            uncertainties.append(UNCERTAINTY_VALUES["assessment"])
                            assess_req_count += 1
                        elif m.original_check_mode == CheckMode.QUICK_CHECK.value:
                            uncertainties.append(UNCERTAINTY_VALUES["quick_check"])
                        else:
                            uncertainties.append(0.0)
                    else:
                        uncertainties.append(0.0)
                        
                else: 
                    c_val = 0.0
                    u_val = 0.0
                    is_usable = (snap and snap.source != "none" and not snap.stale and snap.score is not None and snap.state is not None and snap.state != MasteryState.UNKNOWN)
                    
                    if m.original_group_type == GroupType.GUIDED.value:
                        if not is_usable: 
                            c_val = TARGET_SEVERITY_VALUES["stale_or_unknown"]
                            u_val = UNCERTAINTY_VALUES["stale_or_unknown"]
                        elif snap.score < 0.40: 
                            c_val = TARGET_SEVERITY_VALUES["low_score"]
                    elif m.original_group_type == GroupType.PRACTICE.value:
                        c_val = TARGET_SEVERITY_VALUES["practice"]
                    elif m.original_group_type == GroupType.EXTENSION.value:
                        c_val = TARGET_SEVERITY_VALUES["extension"]
                        
                    severities.append(c_val)
                    missed_ratios.append(0.0)
                    uncertainties.append(u_val)
                    
            if confirmed_gap_count > 0:
                add_reason(f"{confirmed_gap_count} learners have confirmed prerequisite gaps.")
            if missing_gap_evidence > 0:
                add_reason(f"Supporting direct-prerequisite evidence could not be resolved for {missing_gap_evidence} learner(s); severity and missed-instruction contributions defaulted to zero.")
            if assess_req_count > 0:
                add_reason(f"{assess_req_count} learners require an assessment because readiness evidence is insufficient.")
            if missed_sess_sum > 0 and missed_sess_rel > 0:
                avg_miss_rat = round(missed_sess_sum / missed_sess_rel, 2)
                add_reason(f"Affected learners missed {missed_sess_sum} of {missed_sess_rel} relevant prerequisite-session exposures in total (ratio: {avg_miss_rat}).")
                
            avg_sev = sum(severities) / len(severities) if severities else 0.0
            avg_missed = sum(missed_ratios) / len(missed_ratios) if missed_ratios else 0.0
            avg_uncert = sum(uncertainties) / len(uncertainties) if uncertainties else 0.0
            
            comp_raw = COMPLEXITY_VALUES["simple"]
            if g.group_type == GroupType.MIXED_SUPPORT:
                comp_raw = COMPLEXITY_VALUES["mixed_support"]
                add_reason("This group combines multiple underlying learning needs.")
            elif g.mixed_needs:
                comp_raw = COMPLEXITY_VALUES["mixed_needs"]
                add_reason("This group combines multiple underlying learning needs.")
            elif len(set(m.original_group_type for m in g_mems)) > 1:
                comp_raw = COMPLEXITY_VALUES["multiple_original"]
                add_reason("This group contains learners with differing original learning needs due to manual modification.")
                
            reach_raw = min(len(g_mems) / PRIORITY_REFERENCE_GROUP_SIZE, 1.0)
            add_reason(f"This group affects {len(g_mems)} learners.")
            
            c_need = round(PRIORITY_WEIGHTS["instructional_need"] * avg_need, 2)
            c_sev = round(PRIORITY_WEIGHTS["evidence_severity"] * avg_sev, 2)
            c_uncert = round(PRIORITY_WEIGHTS["uncertainty"] * avg_uncert, 2)
            c_missed = round(PRIORITY_WEIGHTS["missed_instruction"] * avg_missed, 2)
            c_comp = round(PRIORITY_WEIGHTS["group_complexity"] * comp_raw, 2)
            c_reach = round(PRIORITY_WEIGHTS["reach"] * reach_raw, 2)
            
            tot = c_need + c_sev + c_uncert + c_missed + c_comp + c_reach
            tot = min(max(tot, 0.0), 100.0)
            tot = round(tot, 2)
            
            max_need = max(needs) if needs else 0.0
            
            calculated_groups.append({
                "group": g,
                "student_count": len(g_mems),
                "score": tot,
                "max_need": max_need,
                "c_need": c_need, "avg_need": avg_need,
                "c_sev": c_sev, "avg_sev": avg_sev,
                "c_uncert": c_uncert, "avg_uncert": avg_uncert,
                "c_missed": c_missed, "avg_missed": avg_missed,
                "c_comp": c_comp, "comp_raw": comp_raw,
                "c_reach": c_reach, "reach_raw": reach_raw,
                "reasons": reasons
            })

        calculated_groups.sort(key=lambda x: (-x["score"], -x["max_need"], x["group"].sort_order, str(x["group"].id)))
        
        if len(calculated_groups) != len(groups):
            raise AppException("PRIORITY_FAILED", "Incomplete calculations", 500)
            
        try:
            self.priority_repo.delete_for_session(session_id)
            
            for idx, cg in enumerate(calculated_groups):
                rank = idx + 1
                score = cg["score"]
                tier = get_tier_for_score(score)
                
                contributions = {
                    "instructional_need": cg["c_need"],
                    "evidence_severity": cg["c_sev"],
                    "uncertainty": cg["c_uncert"],
                    "missed_instruction": cg["c_missed"],
                    "group_complexity": cg["c_comp"],
                    "reach": cg["c_reach"]
                }
                top_reason_key = select_top_factor(contributions)
                
                top_reason = ""
                if top_reason_key == "instructional_need": top_reason = "High foundational learning need among current group members."
                elif top_reason_key == "evidence_severity": top_reason = "Significant severity in current learning gaps."
                elif top_reason_key == "uncertainty": top_reason = "Teacher intervention required to assess uncertain readiness."
                elif top_reason_key == "missed_instruction": top_reason = "High rate of missed prerequisite instruction."
                elif top_reason_key == "group_complexity": top_reason = "Group composition is complex."
                elif top_reason_key == "reach": top_reason = "Group reaches a significant number of learners."
                else: top_reason = "No material priority factor contributed to this score."
                
                db_p = GroupPriority(
                    id=uuid.uuid4(),
                    session_id=session_id,
                    group_id=cg["group"].id,
                    priority_score=score,
                    priority_rank=rank,
                    priority_tier=tier,
                    instructional_need_score=cg["c_need"],
                    evidence_severity_score=cg["c_sev"],
                    uncertainty_score=cg["c_uncert"],
                    missed_instruction_score=cg["c_missed"],
                    group_complexity_score=cg["c_comp"],
                    reach_score=cg["c_reach"],
                    factor_breakdown={
                        "instructional_need": {"raw": cg["avg_need"], "weight": PRIORITY_WEIGHTS["instructional_need"], "contribution": cg["c_need"]},
                        "evidence_severity": {"raw": cg["avg_sev"], "weight": PRIORITY_WEIGHTS["evidence_severity"], "contribution": cg["c_sev"]},
                        "uncertainty": {"raw": cg["avg_uncert"], "weight": PRIORITY_WEIGHTS["uncertainty"], "contribution": cg["c_uncert"]},
                        "missed_instruction": {"raw": cg["avg_missed"], "weight": PRIORITY_WEIGHTS["missed_instruction"], "contribution": cg["c_missed"]},
                        "group_complexity": {"raw": cg["comp_raw"], "weight": PRIORITY_WEIGHTS["group_complexity"], "contribution": cg["c_comp"]},
                        "reach": {"raw": cg["reach_raw"], "weight": PRIORITY_WEIGHTS["reach"], "contribution": cg["c_reach"]}
                    },
                    reasons=cg["reasons"],
                    top_reason=top_reason,
                    student_count_at_generation=cg["student_count"]
                )
                self.db.add(db_p)
                self.db.flush()
                
            pass  # priority_generated_at removed
            pass
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise AppException("PRIORITY_FAILED", str(e), 500)
            
        return self.get_priorities(session_id)

    def get_priorities(self, session_id: UUID) -> SessionPriorityResponse:
        session = self.session_repo.get_by_id(session_id)
        if not session: raise AppException("NOT_FOUND", "Session not found", 404)
        
        db_priorities = self.priority_repo.get_by_session(session_id)
        if not db_priorities:
            return SessionPriorityResponse(
                session_id=session_id, generated=False, stale=False, weights=PRIORITY_WEIGHTS, priorities=[]
            )
            
        memberships = self.mem_repo.get_by_session(session_id)
        member_count_by_group = {}
        for m in memberships:
            member_count_by_group[m.group_id] = member_count_by_group.get(m.group_id, 0) + 1
            
        out_priorities = []
        u, h, m_tier, l = 0, 0, 0, 0
        for p in db_priorities:
            eff_rank = p.teacher_rank if p.teacher_rank is not None else p.priority_rank
            if p.priority_tier == "urgent": u += 1
            elif p.priority_tier == "high": h += 1
            elif p.priority_tier == "moderate": m_tier += 1
            else: l += 1
            
            cur_count = member_count_by_group.get(p.group_id, 0)
            
            out_priorities.append(GroupPriorityResponse(
                group_id=p.group_id, group_name=p.group.name, group_type=p.group.group_type.value,
                priority_rank=p.priority_rank, priority_score=p.priority_score, priority_tier=p.priority_tier,
                teacher_rank=p.teacher_rank, teacher_override_reason=p.teacher_override_reason,
                effective_rank=eff_rank, 
                student_count=p.student_count_at_generation,
                current_student_count=cur_count,
                factor_breakdown=PriorityFactors(**p.factor_breakdown),
                top_reason=p.top_reason, reasons=p.reasons
            ))
            
        out_priorities.sort(key=lambda x: x.effective_rank)
            
        summ = PrioritySummary(groups_ranked=len(out_priorities), urgent=u, high=h, moderate=m_tier, low=l)
        return SessionPriorityResponse(
            session_id=session_id, generated=True, generated_at=None,
            stale=False, weights=PRIORITY_WEIGHTS, priorities=out_priorities, summary=summ
        )
        
    def reorder_priority(self, session_id: UUID, req) -> SessionPriorityResponse:
        session = self.session_repo.get_by_id(session_id)
        if not session: raise AppException("NOT_FOUND", "Session not found", 404)
        if session.status != SessionStatus.GROUPED:
            raise AppException("INVALID_SESSION_STATE", f"Cannot reorder priority for status {session.status}", 400)
            
        pass
        
        db_priorities = self.priority_repo.get_by_session(session_id)
        if not db_priorities: raise AppException("NO_PRIORITIES", "No priorities to reorder.", 404)
        
        db_group_ids = {p.group_id for p in db_priorities}
        req_group_ids = {g_id for g_id in req.ordered_group_ids}
        
        if len(req.ordered_group_ids) != len(req_group_ids):
            raise AppException("VALIDATION_ERROR", "Duplicate group IDs in reorder request.", 400)
        if db_group_ids != req_group_ids:
            raise AppException("VALIDATION_ERROR", "Requested group IDs do not match exact current groups.", 400)
            
        try:
            for idx, g_id in enumerate(req.ordered_group_ids):
                p = next(p for p in db_priorities if p.group_id == g_id)
                p.teacher_rank = idx + 1
                p.teacher_override_reason = req.reason
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise AppException("REORDER_FAILED", str(e), 500)
            
        return self.get_priorities(session_id)

