from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.all_models import RotationPlan, RotationSlot

class RotationRepository:
    def __init__(self, db: Session):
        self.db = db
        
    def get_plan_by_session(self, session_id: UUID) -> Optional[RotationPlan]:
        return self.db.query(RotationPlan).filter(RotationPlan.session_id == session_id).first()
        
    def get_slots_by_plan(self, plan_id: UUID) -> List[RotationSlot]:
        return self.db.query(RotationSlot).filter(RotationSlot.rotation_plan_id == plan_id).order_by(RotationSlot.sequence_index).all()
        
    def add_plan_and_flush(self, plan: RotationPlan):
        self.db.add(plan)
        self.db.flush()
        
    def add_slot_and_flush(self, slot: RotationSlot):
        self.db.add(slot)
        self.db.flush()
        
    def delete_for_session(self, session_id: UUID):
        plan = self.get_plan_by_session(session_id)
        if plan:
            self.db.delete(plan)
            self.db.flush()
