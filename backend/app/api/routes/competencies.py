from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.services.competency_service import CompetencyService
from app.schemas.competency import CompetencyCreate, CompetencyResponse, CompetencyPrerequisiteCreate, CompetencyPrerequisiteResponse
from uuid import UUID

router = APIRouter()

@router.post("", response_model=CompetencyResponse)
def create_competency(schema: CompetencyCreate, db: Session = Depends(get_db)):
    return CompetencyService(db).create_competency(schema)

@router.get("", response_model=list[CompetencyResponse])
def get_competencies(subject: Optional[str] = None, grade: Optional[int] = None, db: Session = Depends(get_db)):
    return CompetencyService(db).get_competencies(subject, grade)

@router.get("/{competency_id}", response_model=CompetencyResponse)
def get_competency(competency_id: UUID, db: Session = Depends(get_db)):
    return CompetencyService(db).get_competency(competency_id)

@router.post("/{competency_id}/prerequisites", response_model=CompetencyPrerequisiteResponse)
def add_prerequisite(competency_id: UUID, schema: CompetencyPrerequisiteCreate, db: Session = Depends(get_db)):
    return CompetencyService(db).add_prerequisite(competency_id, schema)

@router.get("/{competency_id}/prerequisites", response_model=list[CompetencyPrerequisiteResponse])
def get_prerequisites(competency_id: UUID, db: Session = Depends(get_db)):
    return CompetencyService(db).get_prerequisites(competency_id)
