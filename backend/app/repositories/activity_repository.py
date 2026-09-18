from sqlalchemy.orm import Session
from uuid import UUID
from app.models.all_models import ActivityPlan, GroupActivity, ActivitySourceCitation

class ActivityPlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_session_id(self, session_id: UUID) -> ActivityPlan:
        return self.db.query(ActivityPlan).filter(ActivityPlan.session_id == session_id).first()

    def add(self, plan: ActivityPlan):
        self.db.add(plan)

    def flush(self):
        self.db.flush()

class GroupActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, activity: GroupActivity):
        self.db.add(activity)

    def flush(self):
        self.db.flush()

class ActivityCitationRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, citation: ActivitySourceCitation):
        self.db.add(citation)

    def flush(self):
        self.db.flush()
