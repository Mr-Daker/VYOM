"""Lightweight observation, mastery update, and regrouping loop."""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

try:
    from .models import (
        CompetencyRecord,
        Student,
        TeacherObservation,
        score_to_state,
        update_mastery_score,
        validate_iso_date,
    )
except ImportError:
    from models import CompetencyRecord, Student, TeacherObservation, score_to_state, update_mastery_score, validate_iso_date


def record_teacher_observation(
    student: Student,
    competency_id: str,
    observation: str,
    current_date_str: Optional[str] = None,
) -> TeacherObservation:
    if observation not in {"understood", "needs_practice", "not_assessed"}:
        raise ValueError("observation must be understood, needs_practice, or not_assessed")
    observed_on = current_date_str or date.today().isoformat()
    validate_iso_date(observed_on)
    return TeacherObservation(student.id, competency_id, observation, observed_on)


def update_mastery(
    student: Student,
    competency_id: str,
    exit_ticket_passed: Optional[bool],
    teacher_observation: Optional[str] = None,
    current_date_str: Optional[str] = None,
) -> Dict[str, object]:
    """Apply one evidence bundle and return a complete audit record."""

    assessed_on = current_date_str or date.today().isoformat()
    validate_iso_date(assessed_on)
    current = student.competencies.get(competency_id)
    old_score = current.score if current else 0.0
    old_state = current.state if current else score_to_state(0.0)
    new_score, reason = update_mastery_score(old_score, teacher_observation, exit_ticket_passed)
    new_state = score_to_state(new_score)
    student.competencies[competency_id] = CompetencyRecord(
        competency_id=competency_id,
        score=new_score,
        state=new_state,
        last_assessed=assessed_on,
        missed=False,
    )
    if new_state.value == "Mastered" and competency_id in student.missed_concepts:
        student.missed_concepts.remove(competency_id)

    return {
        "student_id": student.id,
        "student_name": student.name,
        "competency_id": competency_id,
        "old_score": old_score,
        "new_score": new_score,
        "old_state": old_state.value,
        "new_state": new_state.value,
        "explanation": (
            f"{student.name}: {old_score:.2f} → {new_score:.2f}. {reason}. "
            f"State: {old_state.value} → {new_state.value}."
        ),
        "date": assessed_on,
    }


def update_many(
    students: List[Student],
    evidence: List[Dict[str, object]],
    assessed_on: str,
) -> List[Dict[str, object]]:
    by_id = {student.id: student for student in students}
    updates: List[Dict[str, object]] = []
    for item in evidence:
        student_id = str(item.get("student_id", ""))
        competency_id = str(item.get("competency_id", ""))
        if student_id not in by_id:
            raise ValueError(f"unknown student: {student_id}")
        if not competency_id:
            raise ValueError("evidence requires competency_id")
        observation = item.get("observation")
        ticket = item.get("exit_ticket_correct")
        if observation in (None, "not_assessed") and ticket is None:
            continue
        updates.append(update_mastery(by_id[student_id], competency_id, ticket, observation, assessed_on))
    return updates


def movement_between(old_groups: List[Dict[str, object]], new_groups: List[object]) -> List[Dict[str, str]]:
    old_lookup = {
        student_id: str(group.get("name", group.get("id", "Previous group")))
        for group in old_groups
        for student_id in group.get("student_ids", [])
    }
    new_lookup = {
        student_id: group.name
        for group in new_groups
        for student_id in group.student_ids
    }
    return [
        {"student_id": student_id, "from": old_lookup.get(student_id, "Not previously grouped"), "to": new_name}
        for student_id, new_name in new_lookup.items()
        if old_lookup.get(student_id) != new_name
    ]


def regroup_after_class(students: List[Student], target_competency_id: str, current_date_str: str):
    try:
        from .engines import build_groups, prioritize_groups
    except ImportError:
        from engines import build_groups, prioritize_groups
    return prioritize_groups(build_groups(students, target_competency_id, current_date_str), students, current_date_str)
