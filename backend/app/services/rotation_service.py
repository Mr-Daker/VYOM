from typing import List, Dict, Any
from uuid import UUID
import math
from sqlalchemy.orm import Session

from app.models.enums import SessionStatus, RotationSlotType
from app.models.all_models import ClassSession, LearningGroup, GroupMembership, GroupPriority, RotationPlan, RotationSlot
from app.core.rotation_config import ROTATION_CONFIG
from app.core.exceptions import AppException
from app.repositories.rotation_repo import RotationRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.grouping_repository import LearningGroupRepository, GroupMembershipRepository
from app.repositories.priority_repository import GroupPriorityRepository

def largest_remainder_allocate(budget_minutes: int, weights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total_weight = sum(w["weight"] for w in weights)
    n = len(weights)
    if total_weight <= 0:
        base = budget_minutes // n
        remainder = budget_minutes % n
        allocations = []
        for w in weights:
            allocations.append({
                "id": w["id"],
                "extra": base,
                "remainder_val": 0,
                "rank": w["effective_rank"]
            })
        allocations.sort(key=lambda x: (x["rank"], str(x["id"])))
        for i in range(remainder):
            allocations[i]["extra"] += 1
        return allocations

    allocations = []
    for w in weights:
        exact = (w["weight"] / total_weight) * budget_minutes
        floor_val = math.floor(exact)
        rem = exact - floor_val
        allocations.append({
            "id": w["id"],
            "extra": floor_val,
            "remainder_val": rem,
            "rank": w["effective_rank"]
        })
        
    allocated = sum(a["extra"] for a in allocations)
    leftover = budget_minutes - allocated
    allocations.sort(key=lambda x: (-x["remainder_val"], x["rank"], str(x["id"])))
    for i in range(leftover):
        allocations[i]["extra"] += 1
    return allocations

class RotationSchedulerService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = RotationRepository(db)
        self.session_repo = SessionRepository(db)
        self.group_repo = LearningGroupRepository(db)
        self.membership_repo = GroupMembershipRepository(db)
        self.priority_repo = GroupPriorityRepository(db)
        
    def generate_rotation(self, session_id: UUID) -> RotationPlan:
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise AppException("NOT_FOUND", "Session not found", 404)
            
        if self.repo.get_plan_by_session(session_id):
            raise AppException("SCHEDULE_ALREADY_EXISTS", "A rotation schedule already exists", 409)

        if session.status != SessionStatus.GROUPED.value:
            raise AppException("INVALID_SESSION_STATE", f"Cannot generate rotation for state {session.status}", 400)
            
        if not session.priority_generated_at:
            raise AppException("PRIORITY_REQUIRED", "Priorities must be generated first", 400)
            
        if session.priority_stale:
            raise AppException("PRIORITY_STALE", "Priorities are stale", 409)
            
        groups = self.group_repo.get_by_session(session_id)
        if not groups:
            raise AppException("SCHEDULE_INVALID_GROUPING", "No groups found in session", 400)
            
        memberships = self.membership_repo.get_by_session(session_id)
        priorities = self.priority_repo.get_by_session(session_id)
        
        if len(priorities) != len(groups):
            raise AppException("SCHEDULE_INVALID_PRIORITY_PLAN", "Mismatched groups and priorities", 400)
            
        priority_map = {p.group_id: p for p in priorities}
        member_counts = {}
        for m in memberships:
            member_counts[m.group_id] = member_counts.get(m.group_id, 0) + 1
            
        effective_ranks = set()
        for g in groups:
            if g.id not in priority_map:
                raise AppException("SCHEDULE_INVALID_PRIORITY_PLAN", "Missing priority for group", 400)
                
            cnt = member_counts.get(g.id, 0)
            if cnt == 0:
                raise AppException("SCHEDULE_INVALID_GROUPING", "Group has zero members", 400)
                
            p = priority_map[g.id]
            if p.student_count_at_generation != cnt:
                raise AppException("PRIORITY_SNAPSHOT_MISMATCH", "Group membership changed since priorities generated", 400)
                
            effective_rank = p.teacher_rank if p.teacher_rank is not None else p.priority_rank
            effective_ranks.add(effective_rank)
            
        if effective_ranks != set(range(1, len(groups) + 1)):
            raise AppException("SCHEDULE_INVALID_PRIORITY_PLAN", "Duplicate or gapped effective ranks", 400)
            
        n = len(groups)
        transitions = max(0, n - 1)
        transition_total = transitions * ROTATION_CONFIG.transition_minutes_each
        overhead = ROTATION_CONFIG.opening_minutes + ROTATION_CONFIG.closing_minutes + transition_total
        budget = session.duration_minutes - overhead
        required_min = n * ROTATION_CONFIG.min_group_attention_minutes
        
        if budget < required_min:
            raise AppException(
                "SCHEDULE_CAPACITY_UNSATISFIABLE", 
                "Not enough time to schedule all groups.", 
                409, 
                details={
                    "duration_minutes": session.duration_minutes,
                    "groups": n,
                    "opening_minutes": ROTATION_CONFIG.opening_minutes,
                    "closing_minutes": ROTATION_CONFIG.closing_minutes,
                    "transition_total_minutes": transition_total,
                    "structural_overhead_minutes": overhead,
                    "required_minimum_attention_minutes": required_min,
                    "minimum_required_session_minutes": overhead + required_min
                }
            )
            
        remaining_budget = budget - required_min
        weights = []
        for g in groups:
            p = priority_map[g.id]
            rank = p.teacher_rank if p.teacher_rank is not None else p.priority_rank
            weights.append({"id": g.id, "weight": p.priority_score, "effective_rank": rank})
            
        extra_allocations = largest_remainder_allocate(remaining_budget, weights)
        alloc_map = {a["id"]: a["extra"] for a in extra_allocations}
        
        sorted_groups = sorted(groups, key=lambda g: priority_map[g.id].teacher_rank if priority_map[g.id].teacher_rank is not None else priority_map[g.id].priority_rank)
        
        plan = RotationPlan(
            session_id=session_id,
            session_duration_minutes=session.duration_minutes,
            opening_minutes=ROTATION_CONFIG.opening_minutes,
            closing_minutes=ROTATION_CONFIG.closing_minutes,
            transition_minutes_each=ROTATION_CONFIG.transition_minutes_each,
            transition_total_minutes=transition_total,
            teacher_attention_budget_minutes=budget,
            minimum_group_attention_minutes=ROTATION_CONFIG.min_group_attention_minutes,
            group_count=n,
            algorithm_version=ROTATION_CONFIG.algorithm_version
        )
        
        slots = []
        time_cursor = 0
        seq = 0
        
        if ROTATION_CONFIG.opening_minutes > 0:
            slots.append(RotationSlot(
                rotation_plan_id=None,
                session_id=session_id,
                sequence_index=seq,
                slot_type=RotationSlotType.WHOLE_CLASS_OPENING.value,
                start_minute=time_cursor,
                end_minute=time_cursor + ROTATION_CONFIG.opening_minutes,
                duration_minutes=ROTATION_CONFIG.opening_minutes
            ))
            time_cursor += ROTATION_CONFIG.opening_minutes
            seq += 1
            
        total_score = sum(p.priority_score for p in priorities)
        for idx, g in enumerate(sorted_groups):
            p = priority_map[g.id]
            extra = alloc_map[g.id]
            base = ROTATION_CONFIG.min_group_attention_minutes
            total = base + extra
            
            if total_score > 0:
                reason = f"Guaranteed {base} minutes plus {extra} weighted minutes from priority score {p.priority_score}."
            else:
                reason = f"Guaranteed {base} minutes plus {extra} minutes from equal-allocation fallback because all priority scores were zero."
                
            slots.append(RotationSlot(
                rotation_plan_id=None,
                session_id=session_id,
                sequence_index=seq,
                slot_type=RotationSlotType.GROUP_VISIT.value,
                group_id=g.id,
                start_minute=time_cursor,
                end_minute=time_cursor + total,
                duration_minutes=total,
                group_name_snapshot=g.name,
                group_type_snapshot=g.group_type,
                priority_score_snapshot=p.priority_score,
                algorithm_priority_rank_snapshot=p.priority_rank,
                teacher_rank_snapshot=p.teacher_rank,
                effective_rank_snapshot=p.teacher_rank if p.teacher_rank is not None else p.priority_rank,
                student_count_snapshot=member_counts[g.id],
                base_minutes=base,
                weighted_extra_minutes=extra,
                reason=reason
            ))
            time_cursor += total
            seq += 1
            
            if idx < n - 1 and ROTATION_CONFIG.transition_minutes_each > 0:
                slots.append(RotationSlot(
                    rotation_plan_id=None,
                    session_id=session_id,
                    sequence_index=seq,
                    slot_type=RotationSlotType.TRANSITION.value,
                    start_minute=time_cursor,
                    end_minute=time_cursor + ROTATION_CONFIG.transition_minutes_each,
                    duration_minutes=ROTATION_CONFIG.transition_minutes_each
                ))
                time_cursor += ROTATION_CONFIG.transition_minutes_each
                seq += 1
                
        if ROTATION_CONFIG.closing_minutes > 0:
            slots.append(RotationSlot(
                rotation_plan_id=None,
                session_id=session_id,
                sequence_index=seq,
                slot_type=RotationSlotType.WHOLE_CLASS_CLOSING.value,
                start_minute=time_cursor,
                end_minute=time_cursor + ROTATION_CONFIG.closing_minutes,
                duration_minutes=ROTATION_CONFIG.closing_minutes
            ))
            time_cursor += ROTATION_CONFIG.closing_minutes

        # Validation of timeline invariants BEFORE persistence
        if len(slots) > 0:
            if slots[0].start_minute != 0:
                raise AppException("ROTATION_GENERATION_FAILED", "First slot does not start at 0", 500)
            if slots[-1].end_minute != session.duration_minutes:
                raise AppException("ROTATION_GENERATION_FAILED", "Last slot does not end at session duration", 500)
            
            for i in range(len(slots)):
                if slots[i].sequence_index != i:
                    raise AppException("ROTATION_GENERATION_FAILED", "Sequence indexes are not contiguous", 500)
                if slots[i].duration_minutes != slots[i].end_minute - slots[i].start_minute:
                    raise AppException("ROTATION_GENERATION_FAILED", "Duration math mismatch", 500)
                if i > 0 and slots[i-1].end_minute != slots[i].start_minute:
                    raise AppException("ROTATION_GENERATION_FAILED", "Gap or overlap in timeline", 500)
                    
            if sum(s.duration_minutes for s in slots) != session.duration_minutes:
                raise AppException("ROTATION_GENERATION_FAILED", "Total duration mismatch", 500)
                
            visit_slots = [s for s in slots if s.slot_type == RotationSlotType.GROUP_VISIT.value]
            if sum(s.duration_minutes for s in visit_slots) != budget:
                raise AppException("ROTATION_GENERATION_FAILED", "Group attention budget mismatch", 500)
            if len(visit_slots) != n:
                raise AppException("ROTATION_GENERATION_FAILED", "Visit count mismatch", 500)
            if set(s.group_id for s in visit_slots) != set(g.id for g in groups):
                raise AppException("ROTATION_GENERATION_FAILED", "Not every group was visited exactly once", 500)

        try:
            self.repo.add_plan_and_flush(plan)
            for s in slots:
                s.rotation_plan_id = plan.id
                self.repo.add_slot_and_flush(s)
                
            session.status = SessionStatus.SCHEDULED.value
            self.db.commit()
        except AppException:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            raise AppException("ROTATION_GENERATION_FAILED", "Failed to persist rotation schedule.", 500, details={"internal_error": str(exc)})
            
        return plan
