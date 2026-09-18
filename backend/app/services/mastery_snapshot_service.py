from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from uuid import UUID
from pydantic import BaseModel

from app.models.enums import MasteryState
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.core.config import settings

READY_THRESHOLD = 0.70
CONFIRMED_GAP_THRESHOLD = 0.40

class MasterySnapshot(BaseModel):
    score: float | None = None
    state: MasteryState | None = None
    confidence: float | None = None
    last_updated: datetime | None = None
    source: str = "none"
    stale: bool = False

class MasterySnapshotService:
    def __init__(self, db):
        self.mastery_repo = MasteryRepository(db)
        self.ev_repo = EvidenceRepository(db)

    def resolve_bulk(
        self, 
        student_ids: List[UUID], 
        competency_ids: List[UUID], 
        as_of_date: datetime
    ) -> Dict[Tuple[UUID, UUID], MasterySnapshot]:
        if not student_ids or not competency_ids:
            return {}

        mastery_records = self.mastery_repo.get_for_students_and_competencies(student_ids, competency_ids)
        mastery_dict = {(m.student_id, m.competency_id): m for m in mastery_records}

        evidence_records = self.ev_repo.get_latest_before_for_students_and_competencies(student_ids, competency_ids, as_of_date)
        evidence_dict = {(e.student_id, e.competency_id): e for e in evidence_records}

        stale_cutoff = as_of_date - timedelta(days=settings.MASTERY_STALE_DAYS)
        result = {}

        for sid in student_ids:
            for cid in competency_ids:
                m = mastery_dict.get((sid, cid))
                e = evidence_dict.get((sid, cid))

                eff_score = None
                eff_state = None
                eff_conf = None
                eff_last_updated = None
                source = "none"

                if m and m.last_updated <= as_of_date:
                    source = "current_mastery"
                    eff_score = m.score
                    eff_state = m.state
                    eff_conf = m.confidence
                    eff_last_updated = m.last_updated
                elif e:
                    source = "historical_evidence"
                    eff_score = e.score
                    if eff_score is not None:
                        if eff_score >= READY_THRESHOLD: eff_state = MasteryState.MASTERED
                        elif eff_score < CONFIRMED_GAP_THRESHOLD: eff_state = MasteryState.NEEDS_SUPPORT
                        else: eff_state = MasteryState.DEVELOPING
                    eff_conf = getattr(e, 'confidence', None)
                    eff_last_updated = e.created_at

                stale = False
                if eff_last_updated and eff_last_updated < stale_cutoff:
                    stale = True

                result[(sid, cid)] = MasterySnapshot(
                    score=eff_score,
                    state=eff_state,
                    confidence=eff_conf,
                    last_updated=eff_last_updated,
                    source=source,
                    stale=stale
                )

        return result
