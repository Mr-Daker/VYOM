from app.repositories.base import BaseRepository
from app.models.all_models import MasteryEvidence
from uuid import UUID

class EvidenceRepository(BaseRepository):
    def add(self, evidence: MasteryEvidence):
        self.db.add(evidence)
        self.db.flush()
        return evidence

    def get_latest_before_for_students_and_competencies(self, student_ids: list[UUID], competency_ids: list[UUID], before_date):
        if not student_ids or not competency_ids: return []
        # We fetch all matching evidence and group/sort in python, or use a distinct-on/window function.
        # Since sqlite and postgres differ on distinct ON, we'll fetch all and filter the latest in python to keep it DB-agnostic.
        records = self.db.query(MasteryEvidence).filter(
            MasteryEvidence.student_id.in_(student_ids),
            MasteryEvidence.competency_id.in_(competency_ids),
            MasteryEvidence.created_at <= before_date
        ).order_by(MasteryEvidence.created_at.desc()).all()
        
        result = {}
        for r in records:
            key = (r.student_id, r.competency_id)
            if key not in result:
                result[key] = r
        return list(result.values())
