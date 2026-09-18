"""Application service layer used by the HTTP server and tests."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

try:
    from .assessment import movement_between, record_teacher_observation, update_many, update_mastery
    from .db import Database, db
    from .engines import build_groups, build_rotation_schedule, prioritize_groups
    from .gap_engine import detect_gaps
    from .generator import generate_activity, generate_exit_ticket, validate_activity
    from .models import (
        ALL_COMPETENCIES,
        Activity,
        ActivityType,
        LearningGroup,
        MasteryState,
        Student,
        to_jsonable,
        validate_iso_date,
    )
except ImportError:
    from assessment import movement_between, record_teacher_observation, update_many, update_mastery
    from db import Database, db
    from engines import build_groups, build_rotation_schedule, prioritize_groups
    from gap_engine import detect_gaps
    from generator import generate_activity, generate_exit_ticket, validate_activity
    from models import ALL_COMPETENCIES, Activity, ActivityType, LearningGroup, MasteryState, Student, to_jsonable, validate_iso_date


EVALUATION_PATH = os.path.join(os.path.dirname(__file__), "..", "evaluation", "results.json")


def _group_from_dict(item: Dict[str, Any]) -> LearningGroup:
    return LearningGroup(
        id=item["id"],
        name=item["name"],
        reason=item["reason"],
        student_ids=list(item["student_ids"]),
        target_competency_id=item["target_competency_id"],
        focus_competency_id=item.get("focus_competency_id", item["target_competency_id"]),
        mastery_level=item["mastery_level"],
        scaffold_language=item.get("scaffold_language", "English"),
        language_breakdown=dict(item.get("language_breakdown", {})),
        priority_score=float(item.get("priority_score", 0)),
        priority_factors=dict(item.get("priority_factors", {})),
        priority_explanation=item.get("priority_explanation", ""),
    )


def _activity_from_dict(item: Dict[str, Any]) -> Activity:
    return Activity(
        id=item["id"],
        title=item["title"],
        objective=item["objective"],
        activity_type=ActivityType(item["activity_type"]),
        competency_id=item["competency_id"],
        target_level=item["target_level"],
        group_id=item["group_id"],
        duration_minutes=int(item["duration_minutes"]),
        materials_needed=list(item["materials_needed"]),
        teacher_involvement_required=bool(item["teacher_involvement_required"]),
        student_instructions=list(item["student_instructions"]),
        expected_response=item["expected_response"],
        quick_check=item["quick_check"],
        source_reference=item["source_reference"],
        language=item.get("language", "English"),
        status=item.get("status", "draft"),
        generated_by=item.get("generated_by", "grounded-template"),
        recovery_reason=item.get("recovery_reason", ""),
    )


class ApiRouter:
    def __init__(self, database: Database = db):
        self.db = database

    def _classroom(self) -> Dict[str, Any]:
        return self.db.read()["classroom"]

    def _present_students(self, students: List[Student], on_date: str) -> List[Student]:
        return [student for student in students if student.was_present(on_date) is not False]

    def _summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        classroom = data["classroom"]
        students = [Student.from_dict(item) for item in data["students"]]
        current_date = classroom["current_date"]
        present = self._present_students(students, current_date)
        gaps = [detect_gaps(student, classroom["target_competency_id"], current_date) for student in present]
        priority = data["groups"][0] if data.get("groups") else None
        return {
            "total_students": len(students),
            "present_count": len(present),
            "absent_count": len(students) - len(present),
            "returning_count": sum(student.returning_after_absence(current_date) for student in present),
            "prerequisite_gap_count": sum(report["recovery_need"] == "High" for report in gaps),
            "group_count": len(data.get("groups", [])),
            "priority_group": priority,
            "target": to_jsonable(ALL_COMPETENCIES[classroom["target_competency_id"]]),
        }

    def get_bootstrap(self) -> Dict[str, Any]:
        data = self.db.snapshot()
        return {
            "classroom": data["classroom"],
            "students": data["students"],
            "groups": data.get("groups", []),
            "latest_plan": data["plans"][-1] if data.get("plans") else None,
            "summary": self._summary(data),
            "competencies": [to_jsonable(item) for item in ALL_COMPETENCIES.values()],
            "demo": data.get("demo", {}),
        }

    def post_reset_demo(self) -> Dict[str, Any]:
        self.db.reset_demo()
        self.db.mark_demo("started_at")
        return self.get_bootstrap()

    def post_classrooms(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        updates: Dict[str, Any] = {}
        if "current_date" in payload:
            updates["current_date"] = validate_iso_date(payload["current_date"])
        if "target_competency_id" in payload:
            if payload["target_competency_id"] not in ALL_COMPETENCIES:
                raise ValueError("unknown target competency")
            updates["target_competency_id"] = payload["target_competency_id"]
        for key, lower, upper in (("class_duration_minutes", 10, 180), ("slot_duration_minutes", 5, 60), ("max_groups", 1, 6)):
            if key in payload:
                value = int(payload[key])
                if not lower <= value <= upper:
                    raise ValueError(f"{key} must be between {lower} and {upper}")
                updates[key] = value
        if "instruction_language" in payload:
            if payload["instruction_language"] not in {"English", "Hindi", "Auto"}:
                raise ValueError("instruction language must be English, Hindi, or Auto")
            updates["instruction_language"] = payload["instruction_language"]
        if "available_materials" in payload:
            materials = payload["available_materials"]
            if not isinstance(materials, list) or not materials or not all(isinstance(item, str) for item in materials):
                raise ValueError("available_materials must be a non-empty list")
            updates["available_materials"] = materials
        return {"classroom": self.db.update_classroom(updates)}

    def post_students(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw = payload.get("students", [])
        if not isinstance(raw, list):
            raise ValueError("students must be a list")
        students = [Student.from_dict(item) for item in raw]
        ids = [student.id for student in students]
        if len(ids) != len(set(ids)):
            raise ValueError("student IDs must be unique")
        self.db.save_students(students)
        return {"status": "saved", "count": len(students)}

    def get_student_mastery(self, student_id: str) -> Dict[str, Any]:
        data = self.db.read()
        student = next((Student.from_dict(item) for item in data["students"] if item["id"] == student_id), None)
        if not student:
            raise KeyError("student not found")
        classroom = data["classroom"]
        return {
            "student": {"id": student.id, "name": student.name, "grade": student.grade},
            "competencies": {key: to_jsonable(value) for key, value in student.competencies.items()},
            "gap_report": detect_gaps(student, classroom["target_competency_id"], classroom["current_date"]),
        }

    def post_attendance(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        classroom = self._classroom()
        attendance_date = validate_iso_date(payload.get("date", classroom["current_date"]))
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("attendance records are required")
        concepts = payload.get("concepts_taught", [classroom["target_competency_id"]])
        self.db.save_attendance(attendance_date, records, concepts)
        self.db.update_classroom({"current_date": attendance_date})
        return {"status": "saved", "present_count": sum(item["present"] for item in records), "date": attendance_date}

    def post_groups_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        classroom = self._classroom()
        competency_id = payload.get("competency_id", classroom["target_competency_id"])
        current_date = payload.get("date", classroom["current_date"])
        max_groups = int(payload.get("max_groups", classroom.get("max_groups", 4)))
        students = self.db.get_students()
        present = self._present_students(students, current_date)
        groups = prioritize_groups(
            build_groups(present, competency_id, current_date, max_groups),
            present,
            current_date,
            payload.get("teacher_overrides", {}),
        )
        serialized = [group.to_dict() for group in groups]
        self.db.save_groups(serialized)
        return {
            "groups": serialized,
            "excluded_absent_student_ids": [student.id for student in students if student not in present],
            "teacher_first": serialized[0] if serialized else None,
        }

    def post_groups_override(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        proposed = payload.get("groups")
        if not isinstance(proposed, list) or not proposed:
            raise ValueError("groups are required")
        data = self.db.read()
        existing = {group["id"]: group for group in data.get("groups", [])}
        expected = sorted(student_id for group in existing.values() for student_id in group["student_ids"])
        assigned = [student_id for group in proposed for student_id in group.get("student_ids", [])]
        if sorted(assigned) != expected or len(assigned) != len(set(assigned)):
            raise ValueError("every present learner must appear exactly once in a group")
        merged = []
        for group in proposed:
            if group.get("id") not in existing:
                raise ValueError("unknown group in override")
            item = dict(existing[group["id"]])
            item["student_ids"] = list(group["student_ids"])
            item["reason"] = item["reason"] + " Teacher reviewed this composition."
            merged.append(item)
        students = self._present_students(self.db.get_students(), data["classroom"]["current_date"])
        prioritized = prioritize_groups([_group_from_dict(item) for item in merged], students, data["classroom"]["current_date"])
        serialized = [group.to_dict() for group in prioritized]
        self.db.save_groups(serialized, "teacher_override")
        return {"groups": serialized, "status": "teacher override saved"}

    def post_schedule_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        started = time.perf_counter()
        data = self.db.read()
        classroom = data["classroom"]
        groups = [_group_from_dict(item) for item in data.get("groups", [])]
        if not groups:
            self.post_groups_generate(payload)
            data = self.db.read()
            groups = [_group_from_dict(item) for item in data["groups"]]
        duration = int(payload.get("class_duration_minutes", classroom["class_duration_minutes"]))
        slot_duration = int(payload.get("slot_duration_minutes", classroom["slot_duration_minutes"]))
        materials = payload.get("available_materials", classroom["available_materials"])
        language = payload.get("language", classroom["instruction_language"])
        schedule = build_rotation_schedule(groups, duration, slot_duration, materials, language)
        tickets = [generate_exit_ticket(group.focus_competency_id, group.id, language if language != "Auto" else group.scaffold_language).to_dict() for group in groups]
        plan = {
            "id": "PLAN-" + uuid.uuid4().hex[:8].upper(),
            "date": classroom["current_date"],
            "target_competency_id": classroom["target_competency_id"],
            "duration_minutes": duration,
            "slot_duration_minutes": slot_duration,
            "language": language,
            "available_materials": materials,
            "groups": [group.to_dict() for group in groups],
            "schedule": [slot.to_dict() for slot in schedule],
            "exit_tickets": tickets,
            "teacher_approved": False,
            "planning_runtime_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        self.db.save_plan(plan)
        return {"plan": plan}

    def post_activities_generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        classroom = self._classroom()
        activity = generate_activity(
            competency_id=payload.get("competency_id", classroom["target_competency_id"]),
            group_mastery_level=payload.get("target_level", "Developing"),
            duration=int(payload.get("duration_minutes", classroom["slot_duration_minutes"])),
            language=payload.get("language", classroom["instruction_language"]),
            materials_available=payload.get("available_materials", classroom["available_materials"]),
            activity_type=ActivityType(payload.get("activity_type", ActivityType.PEER_ACTIVITY.value)),
            group_id=payload.get("group_id", "unassigned"),
            recovery_reason=payload.get("recovery_reason", ""),
            variation=int(payload.get("variation", 0)),
        )
        return {"activity": activity.to_dict()}

    def post_activity_update(self, activity_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = self.db.latest_plan()
        if not plan:
            raise KeyError("no plan exists")
        activity_dict = None
        for slot in plan["schedule"]:
            if slot["activity"]["id"] == activity_id:
                activity_dict = slot["activity"]
                break
        if activity_dict is None:
            raise KeyError("activity not found")
        allowed = {"title", "objective", "student_instructions", "expected_response", "quick_check", "status"}
        for key, value in payload.items():
            if key in allowed:
                activity_dict[key] = value
        activity_dict["generated_by"] = "teacher-edited"
        activity = _activity_from_dict(activity_dict)
        errors = validate_activity(activity, plan["available_materials"], activity.duration_minutes)
        if errors:
            raise ValueError("; ".join(errors))
        self.db.replace_latest_plan(plan, {"type": "activity_edit", "activity_id": activity_id})
        return {"activity": activity_dict, "status": "saved"}

    def post_activity_regenerate(self, activity_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = self.db.latest_plan()
        if not plan:
            raise KeyError("no plan exists")
        for slot in plan["schedule"]:
            current = slot["activity"]
            if current["id"] != activity_id:
                continue
            replacement = generate_activity(
                current["competency_id"], current["target_level"], current["duration_minutes"], current["language"],
                plan["available_materials"], ActivityType(current["activity_type"]), current["group_id"],
                current.get("recovery_reason", ""), int(payload.get("variation", 1)),
            ).to_dict()
            slot["activity"] = replacement
            self.db.replace_latest_plan(plan, {"type": "activity_regenerate", "activity_id": activity_id})
            return {"activity": replacement, "status": "regenerated"}
        raise KeyError("activity not found")

    def post_plan_approval(self, plan_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        plan = self.db.latest_plan()
        if not plan or plan["id"] != plan_id:
            raise KeyError("plan not found")
        approved = bool(payload.get("approved", True))
        if approved and any(slot["activity"].get("status") == "rejected" for slot in plan["schedule"]):
            raise ValueError("the plan contains a rejected activity; edit or regenerate it before approval")
        plan["teacher_approved"] = approved
        for slot in plan["schedule"]:
            slot["activity"]["status"] = "approved" if approved else "rejected"
        self.db.replace_latest_plan(plan, {"type": "plan_approval", "approved": approved})
        return {"plan": plan, "status": "approved" if approved else "rejected"}

    def post_exit_ticket(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        classroom = self._classroom()
        return {"exit_ticket": generate_exit_ticket(
            payload.get("competency_id", classroom["target_competency_id"]),
            payload.get("group_id", "unassigned"),
            payload.get("language", classroom["instruction_language"]),
        ).to_dict()}

    def post_observations(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        observed_on = payload.get("date", self._classroom()["current_date"])
        students = {student.id: student for student in self.db.get_students()}
        observations = [
            record_teacher_observation(students[item["student_id"]], item["competency_id"], item["observation"], observed_on).to_dict()
            for item in payload.get("observations", [])
        ]
        self.db.save_learning_evidence(observations, [], [])
        return {"status": "saved", "count": len(observations)}

    def post_mastery_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        students = self.db.get_students()
        student = next((item for item in students if item.id == payload.get("student_id")), None)
        if not student:
            raise KeyError("student not found")
        update = update_mastery(
            student,
            payload["competency_id"],
            payload.get("exit_ticket_correct"),
            payload.get("observation"),
            payload.get("date", self._classroom()["current_date"]),
        )
        self.db.save_students(students)
        self.db.save_learning_evidence([], [], [update])
        return {"status": "updated", "update": update}

    def post_next_plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self.db.read()
        classroom = data["classroom"]
        students = [Student.from_dict(item) for item in data["students"]]
        assessed_on = payload.get("date", classroom["current_date"])
        evidence = payload.get("evidence", [])
        updates = update_many(students, evidence, assessed_on)
        self.db.save_students(students)
        observations = [
            {"student_id": item["student_id"], "competency_id": item["competency_id"], "observation": item.get("observation"), "date": assessed_on}
            for item in evidence if item.get("observation") not in (None, "not_assessed")
        ]
        assessments = [
            {"student_id": item["student_id"], "competency_id": item["competency_id"], "correct": item.get("exit_ticket_correct"), "date": assessed_on}
            for item in evidence if item.get("exit_ticket_correct") is not None
        ]
        self.db.save_learning_evidence(observations, assessments, updates)

        next_date = payload.get("next_date") or (date.fromisoformat(assessed_on) + timedelta(days=1)).isoformat()
        present_next = [student for student in students if student.was_present(next_date) is not False]
        next_groups = prioritize_groups(
            build_groups(present_next, classroom["target_competency_id"], next_date, classroom["max_groups"]),
            present_next,
            next_date,
        )
        movements = movement_between(data.get("groups", []), next_groups)
        serialized = [group.to_dict() for group in next_groups]
        self.db.update_classroom({"current_date": next_date})
        self.db.save_groups(serialized)
        if any(item["student_id"] == "STU020" for item in updates):
            self.db.mark_demo("completed_at")
        return {"status": "next groups ready", "updates": updates, "groups": serialized, "movements": movements, "next_date": next_date}

    def get_metrics(self) -> Dict[str, Any]:
        if os.path.exists(EVALUATION_PATH):
            with open(EVALUATION_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        return {"status": "evaluation has not been run", "command": "python3 evaluation/run_evaluation.py"}

    def get_analytics(self) -> Dict[str, Any]:
        data = self.db.read()
        mastery = data.get("mastery_history", [])
        needs_support = Counter(item["student_id"] for item in mastery if item["new_state"] != MasteryState.MASTERED.value)
        competency_failures = Counter(item["competency_id"] for item in data.get("assessments", []) if item.get("correct") is False)
        attendance_gaps = Counter(student["id"] for student in data["students"] for entry in student.get("attendance_history", []) if not entry["present"])
        teacher_time = Counter(
            slot["group_id"] for plan in data.get("plans", []) for slot in plan["schedule"]
            if slot["activity"]["teacher_involvement_required"]
        )
        return {
            "repeated_support": needs_support.most_common(8),
            "competencies_needing_review": competency_failures.most_common(),
            "absence_counts": attendance_gaps.most_common(8),
            "teacher_attention_slots": dict(teacher_time),
            "privacy_note": "Aggregated teaching signals only; no learner ranking is shown.",
        }


router = ApiRouter()
