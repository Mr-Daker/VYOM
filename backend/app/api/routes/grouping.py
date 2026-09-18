from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app.services.grouping_service import GroupingService
from app.schemas.grouping import GroupingResponse, GenerateGroupsRequest, MoveStudentRequest, UpdateGroupRequest

router = APIRouter()

@router.post("/sessions/{session_id}/groups/generate", response_model=GroupingResponse)
def generate_groups(session_id: UUID, req: GenerateGroupsRequest, db: Session = Depends(get_db)):
    svc = GroupingService(db)
    return svc.generate_groups(session_id, replace_existing=req.replace_existing, force_replace_teacher_edits=req.force_replace_teacher_edits)

@router.get("/sessions/{session_id}/groups", response_model=GroupingResponse)
def get_groups(session_id: UUID, db: Session = Depends(get_db)):
    svc = GroupingService(db)
    return svc.get_groups(session_id)

@router.post("/sessions/{session_id}/groups/move-student", response_model=GroupingResponse)
def move_student(session_id: UUID, req: MoveStudentRequest, db: Session = Depends(get_db)):
    svc = GroupingService(db)
    return svc.move_student(session_id, req)

@router.patch("/sessions/{session_id}/groups/{group_id}", response_model=GroupingResponse)
def update_group(session_id: UUID, group_id: UUID, req: UpdateGroupRequest, db: Session = Depends(get_db)):
    svc = GroupingService(db)
    return svc.update_group(session_id, group_id, req)
