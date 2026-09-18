"""Run the fixed Saarthi-MG benchmark and write evaluation/results.json."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from engines import build_groups, build_rotation_schedule, prioritize_groups
from gap_engine import detect_gaps
from generator import validate_activity
from models import ALL_COMPETENCIES, MasteryState, Student, score_to_state


def pct(numerator, denominator):
    return round(100 * numerator / denominator, 2) if denominator else 0.0


def load_students(spec):
    with open(os.path.join(ROOT, "demo_scenario.json"), encoding="utf-8") as handle:
        raw = json.load(handle)["students"]
    selected = raw[: max(0, spec["class_size"] - 2)]
    for special in (next(item for item in raw if item["id"] == "STU020"), next(item for item in raw if item["id"] == "STU027")):
        if special not in selected:
            selected.append(special)
    students = [Student.from_dict(item) for item in selected[: spec["class_size"]]]
    for student in students:
        # Keep Rajkumar's recovery story and Vihaan's extension story stable.
        if student.id in {"STU020", "STU027"}:
            continue
        for record in student.competencies.values():
            record.score = round(max(0.0, min(1.0, record.score + spec["score_shift"])), 2)
            record.state = score_to_state(record.score)
    return students


def expected_bucket(student, target, today):
    """Apply the frozen rubric independently of the production gap function."""

    ordered = []
    visited = set()

    def visit(competency_id):
        for prerequisite_id in ALL_COMPETENCIES[competency_id].prerequisites:
            if prerequisite_id in visited:
                continue
            visit(prerequisite_id)
            visited.add(prerequisite_id)
            ordered.append(prerequisite_id)

    visit(target)
    high_gap = False
    for prerequisite_id in ordered:
        record = student.competencies.get(prerequisite_id)
        if record is None:
            high_gap = True
        elif record.state != MasteryState.MASTERED and (record.score < 0.40 or record.missed or prerequisite_id in student.missed_concepts):
            high_gap = True
    if high_gap:
        return "RECOVERY"
    return student.competencies.get(target).state.value if target in student.competencies else MasteryState.NOT_YET.value


def run():
    with open(os.path.join(ROOT, "evaluation", "benchmark_scenarios.json"), encoding="utf-8") as handle:
        scenarios = json.load(handle)

    assignment_total = assignment_ok = constraint_violations = agreement_total = agreement_ok = 0
    gap_total = gap_ok = slots_total = occupied_ok = conflicts = priority_slots = priority_received = utilized_minutes = available_minutes = 0
    activities_total = schema_ok = competency_ok = level_ok = materials_ok = grounded_ok = unsafe_count = 0
    plan_times = []
    accepted_plans = checks_enabled = 0

    for spec in scenarios:
        students = load_students(spec)
        started = time.perf_counter()
        groups = prioritize_groups(build_groups(students, "N6", "2026-09-11", 4), students, "2026-09-11")
        schedule = build_rotation_schedule(groups, spec["duration"], spec["slot"], spec["materials"], spec["language"])
        plan_times.append((time.perf_counter() - started) * 1000)

        assigned = [student_id for group in groups for student_id in group.student_ids]
        assignment_total += len(students)
        assignment_ok += sum(student.id in assigned for student in students)
        constraint_violations += max(0, len(assigned) - len(set(assigned))) + int(len(groups) > 4) + sum(not group.student_ids for group in groups)

        group_by_student = {student_id: group.mastery_level for group in groups for student_id in group.student_ids}
        for student in students:
            expected = expected_bucket(student, "N6", "2026-09-11")
            agreement_total += 1
            agreement_ok += group_by_student.get(student.id) == expected
            reference_gap = any(
                record.state != MasteryState.MASTERED and (record.missed or record.score < .4)
                for competency_id, record in student.competencies.items() if competency_id in {"N1", "N2", "N3", "N4"}
            )
            gap_total += 1
            gap_ok += (detect_gaps(student, "N6", "2026-09-11")["recovery_need"] == "High") == reference_gap

        slot_indexes = sorted({item.slot_index for item in schedule})
        for index in slot_indexes:
            items = [item for item in schedule if item.slot_index == index]
            slots_total += len(groups)
            occupied_ok += len(items)
            conflicts += int(sum(item.activity.teacher_involvement_required for item in items) != 1)
            available_minutes += (items[0].end_minute - items[0].start_minute) * len(groups)
            utilized_minutes += sum(item.end_minute - item.start_minute for item in items)
        priority_slots += 1
        priority_received += any(item.group_id == groups[0].id and item.activity.teacher_involvement_required for item in schedule)

        plan_valid = True
        for item in schedule:
            activity = item.activity
            errors = validate_activity(activity, spec["materials"], activity.duration_minutes)
            activities_total += 1
            schema_ok += not errors
            group = next(group for group in groups if group.id == item.group_id)
            competency_ok += activity.competency_id == group.focus_competency_id
            level_ok += activity.target_level == group.mastery_level
            materials_ok += not (set(activity.materials_needed) - set(spec["materials"]))
            grounded_ok += bool(activity.source_reference)
            unsafe = any("unsafe" in error for error in errors)
            unsafe_count += unsafe
            plan_valid = plan_valid and not errors
            checks_enabled += bool(activity.quick_check)
        accepted_plans += plan_valid

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(scenarios),
        "scope_note": "Deterministic synthetic engineering benchmark; not a teacher study or learning-outcome claim.",
        "summary": {
            "grouping": {
                "student_assignment_rate": pct(assignment_ok, assignment_total),
                "constraint_violations": constraint_violations,
                "independent_rule_rubric_agreement": pct(agreement_ok, agreement_total),
                "prerequisite_gap_accuracy": pct(gap_ok, gap_total),
            },
            "scheduling": {
                "continuous_work_rate": pct(occupied_ok, slots_total),
                "teacher_conflicts": conflicts,
                "priority_group_teacher_access": pct(priority_received, priority_slots),
                "class_time_utilization": pct(utilized_minutes, available_minutes),
            },
            "activities": {
                "schema_success_rate": pct(schema_ok, activities_total),
                "competency_preservation": pct(competency_ok, activities_total),
                "level_appropriateness": pct(level_ok, activities_total),
                "material_compliance": pct(materials_ok, activities_total),
                "curriculum_grounding_rate": pct(grounded_ok, activities_total),
                "unsafe_or_invalid_rate": pct(unsafe_count + activities_total - schema_ok, activities_total),
            },
            "workflow": {
                "median_system_plan_runtime_ms": round(sorted(plan_times)[len(plan_times) // 2], 2),
                "teacher_edits_in_automated_benchmark": 0,
                "plan_acceptance_rate": pct(accepted_plans, len(scenarios)),
                "learning_checks_enabled": checks_enabled,
                "manual_planning_time": "Not yet measured; requires teacher usability study",
            },
        },
        "baseline_comparison": [
            {"name": "Manual blank template", "groups_continuously_occupied": False, "prerequisite_aware": False, "curriculum_sources": False, "validated_constraint_rate": None},
            {"name": "Generic one-shot prompt", "groups_continuously_occupied": False, "prerequisite_aware": False, "curriculum_sources": False, "validated_constraint_rate": None},
            {"name": "Saarthi-MG orchestrator", "groups_continuously_occupied": True, "prerequisite_aware": True, "curriculum_sources": True, "validated_constraint_rate": pct(accepted_plans, len(scenarios))}
        ],
        "baseline_note": "Structural capability comparison, not a measured human-performance comparison. Unmeasured baselines are shown as not tested instead of assigning invented scores.",
    }
    output_path = os.path.join(ROOT, "evaluation", "results.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)
    print(json.dumps(results["summary"], indent=2))


if __name__ == "__main__":
    run()
