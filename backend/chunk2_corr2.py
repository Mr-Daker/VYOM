with open("app/services/gap_detection_service.py", "w") as f:
    f.write("""import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Set, Tuple
from uuid import UUID

from app.services.base import BaseService
from app.repositories.session_repository import SessionRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.competency_repository import CompetencyRepository
from app.repositories.mastery_repository import MasteryRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.models.enums import GapClassification, StudentAnalysisStatus, OverallReadinessStatus, AttendanceStatus, MasteryState
from app.schemas.gap_detection import GapDetectionResponse, StudentGapAssessment, PrerequisiteAssessment, GapDetectionSummary, GapDetectionMetadata
from app.core.exceptions import AppException
from app.core.config import settings

# Thresholds
READY_THRESHOLD = 0.70
CONFIRMED_GAP_THRESHOLD = 0.40

class GapDetectionService(BaseService):
    def __init__(self, db):
        super().__init__(db)
        self.session_repo = SessionRepository(db)
        self.student_repo = StudentRepository(db)
        self.comp_repo = CompetencyRepository(db)
        self.mastery_repo = MasteryRepository(db)
        self.att_repo = AttendanceRepository(db)

    def _build_graph(self):
        prereqs = self.comp_repo.get_all_prerequisites()
        graph = {}
        for p in prereqs:
            if p.competency_id not in graph:
                graph[p.competency_id] = []
            graph[p.competency_id].append(p.prerequisite_competency_id)
        return graph

    def _get_direct_and_transitive(self, graph: Dict[UUID, List[UUID]], target_id: UUID) -> Tuple[List[UUID], List[UUID], List[str]]:
        direct = graph.get(target_id, [])
        transitive = []
        warnings = []
        
        # Ensure direct and transitive sets do not overlap, and target is excluded.
        visited = set(direct)
        visited.add(target_id)
        
        def dfs(node):
            for neighbor in graph.get(node, []):
                if neighbor in visited:
                    warnings.append(f"Cycle detected in prerequisite graph involving competency {neighbor}.")
                else:
                    visited.add(neighbor)
                    transitive.append(neighbor)
                    dfs(neighbor)
        
        for d in direct:
            dfs(d)
            
        # Deduplicate warnings just in case
        warnings = list(set(warnings))
        return direct, transitive, warnings

    def detect_gaps(self, session_id: UUID) -> GapDetectionResponse:
        session = self.session_repo.get_by_id(session_id)
        if not session:
            raise AppException("NOT_FOUND", "Session not found", 404)
        if not session.target_competency_id:
            raise AppException("VALIDATION_ERROR", "Session has no target competency", 400)

        target_comp = self.comp_repo.get_by_id(session.target_competency_id)
        if not target_comp:
            raise AppException("NOT_FOUND", "Target competency not found", 404)

        classroom_id = session.classroom_id
        students = self.student_repo.get_by_classroom(classroom_id)
        active_students = [s for s in students if s.active]
        student_ids = [s.id for s in active_students]

        graph = self._build_graph()
        direct_ids, transitive_ids, warnings = self._get_direct_and_transitive(graph, session.target_competency_id)
        all_prereq_ids = direct_ids + transitive_ids

        all_comps = {c.id: c for c in self.comp_repo.get_all()}
        
        current_atts = {a.student_id: a.status for a in self.att_repo.get_by_session(session_id)}
        
        metadata = GapDetectionMetadata(
            attendance_lookback_days=settings.GAP_ATTENDANCE_LOOKBACK_DAYS,
            mastery_stale_days=settings.MASTERY_STALE_DAYS,
            warnings=warnings
        )
        summary = GapDetectionSummary(students_total=len(active_students))

        if not all_prereq_ids:
            assessments = []
            for s in active_students:
                curr_att = current_atts.get(s.id)
                if not curr_att:
                    status = StudentAnalysisStatus.CURRENT_ATTENDANCE_UNKNOWN
                    overall = OverallReadinessStatus.NOT_ANALYZED
                    summary.attendance_unknown += 1
                elif curr_att == AttendanceStatus.ABSENT:
                    status = StudentAnalysisStatus.NOT_CURRENTLY_AVAILABLE
                    overall = OverallReadinessStatus.NOT_ANALYZED
                    summary.students_absent += 1
                else:
                    status = StudentAnalysisStatus.ANALYZED
                    overall = OverallReadinessStatus.NO_PREREQUISITES
                    summary.students_analyzed += 1
                    summary.no_prerequisites += 1
                    
                assessments.append(StudentGapAssessment(
                    student_id=s.id, student_name=s.name, grade=s.grade,
                    current_attendance=curr_att, analysis_status=status, overall_status=overall
                ))
            return GapDetectionResponse(session_id=session.id, classroom_id=classroom_id, target_competency_id=session.target_competency_id, metadata=metadata, summary=summary, students=assessments)

        # Pre-load bulk data
        mastery_records = self.mastery_repo.get_for_students_and_competencies(student_ids, all_prereq_ids)
        mastery_dict = {}
        for m in mastery_records:
            if m.student_id not in mastery_dict:
                mastery_dict[m.student_id] = {}
            mastery_dict[m.student_id][m.competency_id] = m

        stale_cutoff = session.date - timedelta(days=settings.MASTERY_STALE_DAYS)
        lookback_cutoff = session.date - timedelta(days=settings.GAP_ATTENDANCE_LOOKBACK_DAYS)

        hist_sessions = self.session_repo.get_completed_before(classroom_id, session.date, lookback_cutoff, all_prereq_ids)
        hist_sess_by_comp = {cid: [] for cid in all_prereq_ids}
        for hs in hist_sessions:
            hist_sess_by_comp[hs.target_competency_id].append(hs.id)
            
        all_hist_sess_ids = [hs.id for hs in hist_sessions]
        hist_atts = self.att_repo.get_for_students_and_sessions(student_ids, all_hist_sess_ids)
        att_dict = {} 
        for ha in hist_atts:
            att_dict[(ha.student_id, ha.class_session_id)] = ha.status

        assessments = []

        for s in active_students:
            curr_att = current_atts.get(s.id)
            if not curr_att:
                summary.attendance_unknown += 1
                assessments.append(StudentGapAssessment(
                    student_id=s.id, student_name=s.name, grade=s.grade,
                    current_attendance=None, analysis_status=StudentAnalysisStatus.CURRENT_ATTENDANCE_UNKNOWN,
                    overall_status=OverallReadinessStatus.NOT_ANALYZED
                ))
                continue
            if curr_att == AttendanceStatus.ABSENT:
                summary.students_absent += 1
                assessments.append(StudentGapAssessment(
                    student_id=s.id, student_name=s.name, grade=s.grade,
                    current_attendance=curr_att, analysis_status=StudentAnalysisStatus.NOT_CURRENTLY_AVAILABLE,
                    overall_status=OverallReadinessStatus.NOT_ANALYZED
                ))
                continue
                
            summary.students_analyzed += 1
            
            dir_assessments = []
            trans_assessments = []
            
            def evaluate_prereq(cid, relationship):
                c = all_comps[cid]
                m = mastery_dict.get(s.id, {}).get(cid)
                
                rel_sessions = hist_sess_by_comp[cid]
                p_cnt = a_cnt = l_cnt = u_cnt = 0
                for sid in rel_sessions:
                    st = att_dict.get((s.id, sid))
                    if st == AttendanceStatus.PRESENT: p_cnt += 1
                    elif st == AttendanceStatus.ABSENT: a_cnt += 1
                    elif st == AttendanceStatus.LATE: l_cnt += 1
                    else: u_cnt += 1 # unrecorded

                stale = False
                if m and m.last_updated and m.last_updated < stale_cutoff:
                    stale = True

                reasons = [f"{c.name} is a {relationship} prerequisite for {target_comp.name}."]
                cls = GapClassification.INSUFFICIENT_EVIDENCE
                
                if not m or m.state == MasteryState.UNKNOWN:
                    reasons.append(f"No explicit mastery record exists for {c.name}.")
                elif stale:
                    reasons.append(f"Mastery evidence is stale (older than {settings.MASTERY_STALE_DAYS} days relative to the session).")
                else:
                    if m.score >= READY_THRESHOLD:
                        cls = GapClassification.READY
                        reasons.append(f"Current mastery {m.score} is above readiness threshold {READY_THRESHOLD}.")
                    elif m.score < CONFIRMED_GAP_THRESHOLD:
                        cls = GapClassification.CONFIRMED_GAP
                        reasons.append(f"Current mastery {m.score} is below confirmation threshold {CONFIRMED_GAP_THRESHOLD}.")
                    else:
                        if a_cnt > 0:
                            cls = GapClassification.LIKELY_GAP
                            reasons.append(f"Current mastery {m.score} is developing (below {READY_THRESHOLD}).")
                            reasons.append(f"The student missed {a_cnt} prerequisite session(s) inside the last {settings.GAP_ATTENDANCE_LOOKBACK_DAYS} days.")
                        else:
                            cls = GapClassification.DEVELOPING
                            reasons.append(f"Current mastery {m.score} is developing (below {READY_THRESHOLD}).")
                            reasons.append(f"There are no recorded absences among the {len(rel_sessions)} prerequisite session(s) inside the last {settings.GAP_ATTENDANCE_LOOKBACK_DAYS} days.")

                if a_cnt > 0 and cls == GapClassification.READY:
                    reasons.append(f"Student missed {a_cnt} session(s) in the last {settings.GAP_ATTENDANCE_LOOKBACK_DAYS} days, but existing strong mastery prevents a gap classification.")
                    
                missed_risk = (a_cnt > 0 and cls in [GapClassification.LIKELY_GAP, GapClassification.INSUFFICIENT_EVIDENCE])

                return PrerequisiteAssessment(
                    competency_id=cid, competency_code=c.code, competency_name=c.name,
                    relationship=relationship, mastery_score=m.score if m else None,
                    mastery_state=m.state if m else None, confidence=m.confidence if m else None,
                    last_updated=m.last_updated.isoformat() if m and m.last_updated else None,
                    stale=stale, classification=cls,
                    relevant_sessions=len(rel_sessions), present_sessions=p_cnt, absent_sessions=a_cnt, late_sessions=l_cnt,
                    attendance_unrecorded_sessions=u_cnt,
                    missed_instruction_risk=missed_risk, reasons=reasons
                )

            for cid in direct_ids:
                dir_assessments.append(evaluate_prereq(cid, "direct"))
            for cid in transitive_ids:
                trans_assessments.append(evaluate_prereq(cid, "transitive"))

            # Rollup rules based strictly on direct prerequisites
            overall = OverallReadinessStatus.READY
            rec_recovery = rec_quick = rec_assess = False
            
            d_classes = [da.classification for da in dir_assessments]
            
            if GapClassification.CONFIRMED_GAP in d_classes or GapClassification.LIKELY_GAP in d_classes:
                overall = OverallReadinessStatus.NEEDS_SUPPORT
                rec_recovery = True
            elif GapClassification.DEVELOPING in d_classes or GapClassification.INSUFFICIENT_EVIDENCE in d_classes:
                overall = OverallReadinessStatus.NEEDS_CHECK
                if GapClassification.DEVELOPING in d_classes: rec_quick = True
                if GapClassification.INSUFFICIENT_EVIDENCE in d_classes: rec_assess = True
            else:
                overall = OverallReadinessStatus.READY
                
            reasons = []
            if overall == OverallReadinessStatus.READY:
                reasons.append("All direct prerequisites are mastered.")
            elif overall == OverallReadinessStatus.NEEDS_SUPPORT:
                reasons.append("One or more direct prerequisites indicate a confirmed or likely gap.")
            elif overall == OverallReadinessStatus.NEEDS_CHECK:
                reasons.append("One or more direct prerequisites require a quick check or initial assessment.")

            if overall == OverallReadinessStatus.READY: summary.ready += 1
            elif overall == OverallReadinessStatus.NEEDS_SUPPORT: summary.needs_support += 1
            elif overall == OverallReadinessStatus.NEEDS_CHECK: summary.needs_check += 1

            assessments.append(StudentGapAssessment(
                student_id=s.id, student_name=s.name, grade=s.grade,
                current_attendance=curr_att, analysis_status=StudentAnalysisStatus.ANALYZED,
                overall_status=overall,
                recovery_recommended=rec_recovery, quick_check_recommended=rec_quick, assessment_recommended=rec_assess,
                direct_prerequisites=dir_assessments, transitive_context=trans_assessments, reasons=reasons
            ))
            
        return GapDetectionResponse(session_id=session.id, classroom_id=classroom_id, target_competency_id=session.target_competency_id, metadata=metadata, summary=summary, students=assessments)
""")
