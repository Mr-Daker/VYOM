import re

with open("app/services/gap_detection_service.py", "r") as f:
    content = f.read()

# Add import
content = content.replace(
    "from app.repositories.evidence_repository import EvidenceRepository",
    "from app.repositories.evidence_repository import EvidenceRepository\nfrom app.services.mastery_snapshot_service import MasterySnapshotService"
)

# Add init
content = content.replace(
    "self.ev_repo = EvidenceRepository(db)",
    "self.ev_repo = EvidenceRepository(db)\n        self.snapshot_service = MasterySnapshotService(db)"
)

# Replace data loading
old_bulk_loading = """        # Pre-load bulk data
        mastery_records = self.mastery_repo.get_for_students_and_competencies(student_ids, all_prereq_ids)
        mastery_dict = {}
        for m in mastery_records:
            if m.student_id not in mastery_dict:
                mastery_dict[m.student_id] = {}
            mastery_dict[m.student_id][m.competency_id] = m
            
        evidence_records = self.ev_repo.get_latest_before_for_students_and_competencies(student_ids, all_prereq_ids, session.date)
        evidence_dict = {}
        for e in evidence_records:
            if e.student_id not in evidence_dict:
                evidence_dict[e.student_id] = {}
            evidence_dict[e.student_id][e.competency_id] = e"""

new_bulk_loading = """        # Pre-load bulk data
        # We also need mastery_dict for the raw `m.last_updated > session.date` reason check
        mastery_records = self.mastery_repo.get_for_students_and_competencies(student_ids, all_prereq_ids)
        raw_mastery_dict = {(m.student_id, m.competency_id): m for m in mastery_records}
        
        snapshots = self.snapshot_service.resolve_bulk(student_ids, all_prereq_ids, session.date)"""

content = content.replace(old_bulk_loading, new_bulk_loading)

# Replace evaluate_prereq logic
old_eval_start = """                c = all_comps[cid]
                m = mastery_dict.get(s.id, {}).get(cid)
                e = evidence_dict.get(s.id, {}).get(cid)
                
                # Determine mastery source and effective values
                mastery_source = "none"
                eff_score = None
                eff_state = None
                eff_conf = None
                eff_last_updated = None
                
                if m and m.last_updated <= session.date:
                    mastery_source = "current_mastery"
                    eff_score = m.score
                    eff_state = m.state
                    eff_conf = m.confidence
                    eff_last_updated = m.last_updated
                elif e:
                    mastery_source = "historical_evidence"
                    eff_score = e.score
                    eff_conf = getattr(e, 'confidence', None)
                    # We infer a basic state from the score if historical state isn't strictly tracked, 
                    # but evidence doesn't always have a guaranteed state enum attached directly to score in same way.
                    # We use the standard thresholds to infer the state:
                    if eff_score >= READY_THRESHOLD: eff_state = MasteryState.MASTERED
                    elif eff_score < CONFIRMED_GAP_THRESHOLD: eff_state = MasteryState.NEEDS_SUPPORT
                    else: eff_state = MasteryState.DEVELOPING
                    eff_last_updated = e.created_at"""

new_eval_start = """                c = all_comps[cid]
                raw_m = raw_mastery_dict.get((s.id, cid))
                snap = snapshots.get((s.id, cid))
                
                mastery_source = snap.source if snap else "none"
                eff_score = snap.score if snap else None
                eff_state = snap.state if snap else None
                eff_conf = snap.confidence if snap else None
                eff_last_updated = snap.last_updated if snap else None"""

content = content.replace(old_eval_start, new_eval_start)

# Replace references to stale and raw_m
content = content.replace("stale = False", "stale = snap.stale if snap else False")
content = content.replace("""                if eff_last_updated and eff_last_updated < stale_cutoff:
                    stale = True""", "")

content = content.replace("if m and m.last_updated > session.date:", "if raw_m and raw_m.last_updated > session.date:")

with open("app/services/gap_detection_service.py", "w") as f:
    f.write(content)
