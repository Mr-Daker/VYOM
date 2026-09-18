from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app.schemas.rotation import RotationPlanResponse, RotationConfigResponse, RotationSummary, GroupRotationAllocation, RotationSlotResponse
from app.services.rotation_service import RotationSchedulerService
from app.repositories.rotation_repo import RotationRepository

router = APIRouter()

def _build_response(plan, slots) -> RotationPlanResponse:
    config_resp = RotationConfigResponse(
        opening_minutes=plan.opening_minutes,
        closing_minutes=plan.closing_minutes,
        transition_minutes=plan.transition_minutes_each,
        minimum_group_attention_minutes=plan.minimum_group_attention_minutes
    )
    
    alloc_minutes = sum(s.duration_minutes for s in slots if s.slot_type == "group_visit")
    
    summary = RotationSummary(
        group_count=plan.group_count,
        teacher_attention_budget_minutes=plan.teacher_attention_budget_minutes,
        transition_total_minutes=plan.transition_total_minutes,
        allocated_teacher_minutes=alloc_minutes
    )
    
    group_allocs = []
    for s in slots:
        if s.slot_type == "group_visit":
            group_allocs.append(GroupRotationAllocation(
                group_id=s.group_id,
                group_name=s.group_name_snapshot,
                group_type=s.group_type_snapshot,
                priority_score=s.priority_score_snapshot,
                algorithm_priority_rank=s.algorithm_priority_rank_snapshot,
                teacher_rank=s.teacher_rank_snapshot,
                effective_rank=s.effective_rank_snapshot,
                student_count=s.student_count_snapshot,
                base_minutes=s.base_minutes,
                weighted_extra_minutes=s.weighted_extra_minutes,
                allocated_teacher_minutes=s.duration_minutes,
                independent_minutes=plan.session_duration_minutes - s.duration_minutes,
                reason=s.reason
            ))
            
    slot_resps = []
    for s in slots:
        slot_resps.append(RotationSlotResponse(
            sequence_index=s.sequence_index,
            slot_type=s.slot_type,
            start_minute=s.start_minute,
            end_minute=s.end_minute,
            duration_minutes=s.duration_minutes,
            group_id=s.group_id,
            reason=s.reason
        ))
        
    return RotationPlanResponse(
        session_id=plan.session_id,
        generated=True,
        session_duration_minutes=plan.session_duration_minutes,
        configuration=config_resp,
        summary=summary,
        group_allocations=group_allocs,
        slots=slot_resps
    )

@router.post("/{session_id}/rotation/generate", response_model=RotationPlanResponse)
def generate_rotation(session_id: UUID, db: Session = Depends(get_db)):
    svc = RotationSchedulerService(db)
    plan = svc.generate_rotation(session_id)
    slots = svc.repo.get_slots_by_plan(plan.id)
    return _build_response(plan, slots)

from app.repositories.session_repository import SessionRepository
from app.core.exceptions import AppException

@router.get("/{session_id}/rotation", response_model=RotationPlanResponse)
def get_rotation(session_id: UUID, db: Session = Depends(get_db)):
    session_repo = SessionRepository(db)
    session = session_repo.get_by_id(session_id)
    if not session:
        raise AppException("NOT_FOUND", "Session not found", 404)
        
    repo = RotationRepository(db)
    plan = repo.get_plan_by_session(session_id)
    if not plan:
        return RotationPlanResponse(session_id=session_id, generated=False)
        
    slots = repo.get_slots_by_plan(plan.id)
    return _build_response(plan, slots)
