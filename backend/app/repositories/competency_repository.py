from app.repositories.base import BaseRepository
from app.models.all_models import Competency, CompetencyPrerequisite
from uuid import UUID

class CompetencyRepository(BaseRepository):
    def get_by_id(self, comp_id: UUID) -> Competency | None:
        return self.db.query(Competency).filter(Competency.id == comp_id).first()
        
    def get_all(self, subject: str = None, grade: int = None):
        q = self.db.query(Competency)
        if subject: q = q.filter(Competency.subject == subject)
        if grade: q = q.filter(Competency.grade == grade)
        return q.all()
        
    def add(self, comp: Competency):
        self.db.add(comp)
        self.db.flush()
        return comp

    def add_prerequisite(self, prereq: CompetencyPrerequisite):
        self.db.add(prereq)
        self.db.flush()
        return prereq
        
    def get_prerequisites(self, comp_id: UUID):
        return self.db.query(CompetencyPrerequisite).filter(CompetencyPrerequisite.competency_id == comp_id).all()

    def get_all_prerequisites(self):
        from app.models.all_models import CompetencyPrerequisite
        return self.db.query(CompetencyPrerequisite).all()
