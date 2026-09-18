from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_db
from app.schemas.activity import ActivityGenerationRequest, ActivityPlanResponse
from app.services.activity_generation import ActivityGenerationService, ActivityQueryService
from app.services.curriculum_retrieval import CurriculumRetrievalService
from app.services.llm.factory import get_llm_provider
from app.services.llm.base import LLMProvider

router = APIRouter()

@router.post("/{session_id}/activities/generate", response_model=ActivityPlanResponse)
def generate_activities(
    request: ActivityGenerationRequest,
    session_id: UUID = Path(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider)
):
    retrieval_service = CurriculumRetrievalService(db)
    service = ActivityGenerationService(db, llm, retrieval_service)
    return service.generate_activities(session_id, request)

@router.get("/{session_id}/activities", response_model=ActivityPlanResponse)
def get_activities(
    session_id: UUID = Path(...),
    db: Session = Depends(get_db)
):
    service = ActivityQueryService(db)
    return service.get_activities(session_id)
