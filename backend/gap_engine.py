"""Explainable prerequisite and attendance-gap detection."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Set

try:
    from .models import ALL_COMPETENCIES, MasteryState, Student, validate_iso_date
except ImportError:  # Direct script/test execution from backend/
    from models import ALL_COMPETENCIES, MasteryState, Student, validate_iso_date


STALE_AFTER_DAYS = 14


def prerequisite_closure(competency_id: str) -> List[str]:
    """Return all prerequisites in teaching order, without duplicates."""

    if competency_id not in ALL_COMPETENCIES:
        raise ValueError(f"unknown competency: {competency_id}")
    ordered: List[str] = []
    visited: Set[str] = set()

    def visit(current_id: str) -> None:
        for prerequisite_id in ALL_COMPETENCIES[current_id].prerequisites:
            if prerequisite_id not in ALL_COMPETENCIES:
                raise ValueError(f"unknown prerequisite {prerequisite_id} on {current_id}")
            if prerequisite_id in visited:
                continue
            visit(prerequisite_id)
            visited.add(prerequisite_id)
            ordered.append(prerequisite_id)

    visit(competency_id)
    return ordered


def detect_gaps(student: Student, target_competency_id: str, current_date_str: str) -> Dict[str, Any]:
    """Combine mastery, recency, and missed lessons without equating absence to failure."""

    validate_iso_date(current_date_str, "current_date")
    current_date = date.fromisoformat(current_date_str)
    prerequisite_ids = prerequisite_closure(target_competency_id)
    missing: List[Dict[str, Any]] = []
    stale: List[str] = []

    for prerequisite_id in prerequisite_ids:
        record = student.competencies.get(prerequisite_id)
        is_mastered = bool(record and record.state == MasteryState.MASTERED)
        missed_lesson = prerequisite_id in student.missed_concepts or bool(record and record.missed)
        days_since_assessed = None
        if record and record.last_assessed:
            days_since_assessed = max(0, (current_date - date.fromisoformat(record.last_assessed)).days)
            if days_since_assessed >= STALE_AFTER_DAYS:
                stale.append(prerequisite_id)

        if not is_mastered:
            missing.append(
                {
                    "prereq_id": prerequisite_id,
                    "description": ALL_COMPETENCIES[prerequisite_id].description,
                    "missed_lesson": missed_lesson,
                    "current_state": record.state.value if record else MasteryState.NOT_YET.value,
                    "score": record.score if record else None,
                    "days_since_assessed": days_since_assessed,
                    "uncertainty": "needs verification" if record is None or prerequisite_id in stale else "observed evidence available",
                }
            )

    direct_missing = [
        item for item in missing if item["prereq_id"] in ALL_COMPETENCIES[target_competency_id].prerequisites
    ]
    missed_missing = [item for item in missing if item["missed_lesson"]]
    very_low = [item for item in missing if item["score"] is None or item["score"] < 0.40]

    if missed_missing or very_low:
        recovery_need = "High"
    elif direct_missing:
        recovery_need = "Medium"
    else:
        recovery_need = "Low"

    if recovery_need == "High":
        readiness = "Not ready - possible prerequisite gap"
    elif recovery_need == "Medium":
        readiness = "Needs guided verification"
    else:
        readiness = "Ready"
    if stale:
        readiness += "; insufficient recent evidence"

    focus_competency_id = missing[-1]["prereq_id"] if missing else target_competency_id
    return {
        "student_id": student.id,
        "target_competency": target_competency_id,
        "missing_prerequisites": missing,
        "direct_missing_prerequisites": direct_missing,
        "stale_competencies": stale,
        "stale_evidence": bool(stale),
        "recovery_need": recovery_need,
        "current_readiness": readiness,
        "focus_competency_id": focus_competency_id,
        "returning_after_absence": student.returning_after_absence(current_date_str),
    }
