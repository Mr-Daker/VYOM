"""Deterministic grouping, teacher-priority, and rotation engines."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Optional

try:
    from .gap_engine import detect_gaps
    from .models import (
        ALL_COMPETENCIES,
        ActivityType,
        LearningGroup,
        MasteryState,
        RotationSlot,
        Student,
    )
except ImportError:
    from gap_engine import detect_gaps
    from models import ALL_COMPETENCIES, ActivityType, LearningGroup, MasteryState, RotationSlot, Student


BUCKET_ORDER = ["RECOVERY", MasteryState.NOT_YET.value, MasteryState.DEVELOPING.value, MasteryState.MASTERED.value]


def _group_label(bucket: str) -> str:
    return {
        "RECOVERY": "Prerequisite recovery",
        MasteryState.NOT_YET.value: "Concept launch",
        MasteryState.DEVELOPING.value: "Guided practice",
        MasteryState.MASTERED.value: "Extension",
    }[bucket]


def _majority_language(students: Iterable[Student]) -> str:
    counts = Counter(student.home_language for student in students)
    return sorted(counts, key=lambda language: (-counts[language], language))[0] if counts else "English"


def build_groups(
    students: List[Student],
    target_competency_id: str,
    current_date: str,
    max_groups: int = 4,
) -> List[LearningGroup]:
    """Group present learners by need. Language only selects the scaffold."""

    if target_competency_id not in ALL_COMPETENCIES:
        raise ValueError(f"unknown competency: {target_competency_id}")
    if not 1 <= max_groups <= 6:
        raise ValueError("max_groups must be between 1 and 6")
    if not students:
        return []

    buckets: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for student in sorted(students, key=lambda item: item.id):
        gap = detect_gaps(student, target_competency_id, current_date)
        target_record = student.competencies.get(target_competency_id)
        target_state = target_record.state if target_record else MasteryState.NOT_YET
        bucket = "RECOVERY" if gap["recovery_need"] == "High" else target_state.value
        buckets[bucket].append({"student": student, "gap": gap})

    populated = [bucket for bucket in BUCKET_ORDER if buckets.get(bucket)]
    # If a teacher chooses fewer groups, combine the least urgent adjacent needs.
    while len(populated) > max_groups:
        source = populated.pop()
        destination = populated[-1]
        buckets[destination].extend(buckets.pop(source))

    groups: List[LearningGroup] = []
    for index, bucket in enumerate(populated):
        entries = buckets[bucket]
        group_students = [entry["student"] for entry in entries]
        gaps = [entry["gap"] for entry in entries]
        language_breakdown = dict(sorted(Counter(student.home_language for student in group_students).items()))
        focus_counts = Counter(gap["focus_competency_id"] for gap in gaps)
        focus_id = sorted(focus_counts, key=lambda item: (-focus_counts[item], item))[0]
        missed_count = sum(1 for gap in gaps if any(item["missed_lesson"] for item in gap["missing_prerequisites"]))

        if bucket == "RECOVERY":
            reason = (
                f"{len(group_students)} learners have a possible prerequisite gap in {focus_id} "
                f"({ALL_COMPETENCIES[focus_id].description.lower()}); {missed_count} also missed related practice. "
                "Verify with the quick check before advancing."
            )
        elif bucket == MasteryState.NOT_YET.value:
            reason = f"These learners are beginning {target_competency_id} and need a concrete model before independent work."
        elif bucket == MasteryState.DEVELOPING.value:
            reason = f"These learners have partial evidence for {target_competency_id} and need guided or peer practice."
        else:
            reason = f"These learners have mastered {target_competency_id} and are ready to apply it in a new problem."

        group = LearningGroup(
            id=f"G{index + 1}",
            name=f"Group {chr(65 + index)} · {_group_label(bucket)}",
            reason=reason,
            student_ids=[student.id for student in group_students],
            target_competency_id=target_competency_id,
            focus_competency_id=focus_id if bucket == "RECOVERY" else target_competency_id,
            mastery_level=bucket,
            scaffold_language=_majority_language(group_students),
            language_breakdown=language_breakdown,
        )
        groups.append(group)

    assigned = [student_id for group in groups for student_id in group.student_ids]
    expected = [student.id for student in students]
    if sorted(assigned) != sorted(expected) or len(assigned) != len(set(assigned)):
        raise RuntimeError("grouping invariant failed: every learner must appear exactly once")
    if len(groups) > max_groups:
        raise RuntimeError("grouping invariant failed: maximum group count exceeded")
    return groups


def prioritize_groups(
    groups: List[LearningGroup],
    students: List[Student],
    current_date: str,
    teacher_overrides: Optional[Dict[str, float]] = None,
) -> List[LearningGroup]:
    """Rank scarce teacher attention using visible, bounded factors."""

    by_id = {student.id: student for student in students}
    teacher_overrides = teacher_overrides or {}
    for group in groups:
        members = [by_id[student_id] for student_id in group.student_ids if student_id in by_id]
        gap_reports = [detect_gaps(student, group.target_competency_id, current_date) for student in members]
        gap_ratio = sum(1 for report in gap_reports if report["recovery_need"] == "High") / max(1, len(members))
        target_scores = [
            student.competencies[group.target_competency_id].score
            if group.target_competency_id in student.competencies
            else 0.0
            for student in members
        ]
        average_mastery = sum(target_scores) / max(1, len(target_scores))
        returning_ratio = sum(1 for report in gap_reports if report["returning_after_absence"]) / max(1, len(members))
        stale_ratio = sum(1 for report in gap_reports if report["stale_evidence"]) / max(1, len(members))
        dependency_urgency = 1.0 if gap_ratio and ALL_COMPETENCIES[group.target_competency_id].prerequisites else 0.0
        override = max(-3.0, min(3.0, float(teacher_overrides.get(group.id, 0.0))))

        factors = {
            "prerequisite_gap": round(gap_ratio * 5.0, 2),
            "low_mastery": round((1.0 - average_mastery) * 3.0, 2),
            "returning_after_absence": round(returning_ratio * 2.0, 2),
            "stale_evidence": round(stale_ratio * 1.0, 2),
            "upcoming_dependency": dependency_urgency,
            "teacher_override": override,
        }
        group.priority_factors = factors
        group.priority_score = round(sum(factors.values()), 2)
        positive = [f"{key.replace('_', ' ')} +{value:g}" for key, value in factors.items() if value > 0]
        group.priority_explanation = (
            f"Priority {group.priority_score:g}: " + ", ".join(positive)
            if positive
            else "Priority 0: independent extension is appropriate"
        )

    return sorted(groups, key=lambda group: (-group.priority_score, group.id))


def _independent_type(group: LearningGroup, slot_index: int) -> ActivityType:
    if group.mastery_level == MasteryState.MASTERED.value:
        return ActivityType.EXTENSION_ACTIVITY
    if group.mastery_level == MasteryState.DEVELOPING.value:
        return ActivityType.PEER_ACTIVITY if slot_index % 2 == 0 else ActivityType.INDEPENDENT_WORKSHEET
    if group.mastery_level == "RECOVERY":
        return ActivityType.PEER_ACTIVITY if slot_index % 2 == 0 else ActivityType.MANIPULATIVE_ACTIVITY
    return ActivityType.MANIPULATIVE_ACTIVITY if slot_index % 2 == 0 else ActivityType.INDEPENDENT_WORKSHEET


def build_rotation_schedule(
    groups: List[LearningGroup],
    class_duration_minutes: int,
    slot_duration_minutes: int = 15,
    available_materials: Optional[List[str]] = None,
    language: str = "English",
) -> List[RotationSlot]:
    """Create a conflict-free matrix with one teacher station per time slot."""

    if not groups:
        raise ValueError("at least one group is required")
    if class_duration_minutes < 10 or class_duration_minutes > 180:
        raise ValueError("class duration must be between 10 and 180 minutes")
    if slot_duration_minutes < 5 or slot_duration_minutes > class_duration_minutes:
        raise ValueError("slot duration must be between 5 minutes and the class duration")
    available_materials = available_materials or ["paper", "pencils", "chalk", "blackboard"]

    try:
        from .generator import generate_activity
    except ImportError:
        from generator import generate_activity

    ranked = sorted(groups, key=lambda group: (-group.priority_score, group.id))
    boundaries = list(range(0, class_duration_minutes, slot_duration_minutes))
    schedule: List[RotationSlot] = []
    for slot_index, start in enumerate(boundaries):
        end = min(class_duration_minutes, start + slot_duration_minutes)
        teacher_group = ranked[slot_index] if slot_index < len(ranked) else ranked[slot_index % len(ranked)]
        for group in ranked:
            with_teacher = group.id == teacher_group.id
            if with_teacher:
                activity_type = ActivityType.RECOVERY_ACTIVITY if group.mastery_level == "RECOVERY" else ActivityType.GUIDED_PRACTICE
                station = "Teacher station"
            else:
                activity_type = _independent_type(group, slot_index)
                station = "Peer station" if activity_type == ActivityType.PEER_ACTIVITY else "Independent station"
            activity = generate_activity(
                competency_id=group.focus_competency_id,
                group_mastery_level=group.mastery_level,
                duration=end - start,
                language=language if language != "Auto" else group.scaffold_language,
                materials_available=available_materials,
                activity_type=activity_type,
                group_id=group.id,
                recovery_reason=group.reason if group.mastery_level == "RECOVERY" else "",
                variation=slot_index,
            )
            schedule.append(RotationSlot(slot_index, start, end, group.id, station, activity))

    for slot_index in range(len(boundaries)):
        slot_items = [item for item in schedule if item.slot_index == slot_index]
        if len(slot_items) != len(groups) or sum(item.activity.teacher_involvement_required for item in slot_items) != 1:
            raise RuntimeError("scheduling invariant failed")
    return schedule
