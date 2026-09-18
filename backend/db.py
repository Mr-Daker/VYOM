"""Atomic JSON persistence for the hackathon prototype."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from .models import AttendanceEntry, Student, to_jsonable
except ImportError:
    from models import AttendanceEntry, Student, to_jsonable


PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB_PATH = os.path.join(PROJECT_DIR, "data", "database.json")
DEMO_PATH = os.path.join(PROJECT_DIR, "demo_scenario.json")
SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Optional[str] = None, demo_path: Optional[str] = None):
        self.path = path or os.getenv("SAARTHI_DB_PATH", DEFAULT_DB_PATH)
        self.demo_path = demo_path or DEMO_PATH
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._ensure_database()

    def _ensure_database(self) -> None:
        with self._lock:
            if not os.path.exists(self.path):
                self.reset_demo()
                return
            try:
                data = self.read()
            except (OSError, json.JSONDecodeError):
                self.reset_demo()
                return
            if data.get("schema_version") != SCHEMA_VERSION:
                self.reset_demo()

    def _initial_data(self) -> Dict[str, Any]:
        with open(self.demo_path, "r", encoding="utf-8") as handle:
            scenario = json.load(handle)
        classroom = {
            "id": "CLASS-DEMO",
            "name": scenario["scenario_name"],
            "teacher_name": scenario["teacher_name"],
            "current_date": scenario["today"],
            "target_competency_id": scenario["todays_objective"],
            "class_duration_minutes": scenario["class_duration_minutes"],
            "slot_duration_minutes": 15,
            "instruction_language": "English",
            "available_materials": scenario["available_materials"],
            "supported_languages": ["English", "Hindi"],
            "max_groups": 4,
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": _now(),
            "classroom": classroom,
            "students": scenario["students"],
            "groups": [],
            "plans": [],
            "attendance": [],
            "observations": [],
            "assessments": [],
            "mastery_history": [],
            "teacher_edits": [],
            "generation_failures": [],
            "demo": {"started_at": None, "completed_at": None},
        }

    def read(self) -> Dict[str, Any]:
        with self._lock, open(self.path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def write(self, data: Dict[str, Any]) -> None:
        payload = to_jsonable(data)
        payload["schema_version"] = SCHEMA_VERSION
        payload["updated_at"] = _now()
        with self._lock:
            fd, temp_path = tempfile.mkstemp(prefix="saarthi-db-", suffix=".json", dir=os.path.dirname(self.path))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    def reset_demo(self) -> Dict[str, Any]:
        with self._lock:
            data = self._initial_data()
            self.write(data)
            return data

    def snapshot(self) -> Dict[str, Any]:
        return self.read()

    def get_students(self) -> List[Student]:
        return [Student.from_dict(item) for item in self.read().get("students", [])]

    def save_students(self, students: List[Student]) -> None:
        with self._lock:
            data = self.read()
            data["students"] = [student.to_dict() for student in students]
            self.write(data)

    def update_classroom(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            data = self.read()
            data["classroom"].update(updates)
            self.write(data)
            return data["classroom"]

    def save_attendance(self, attendance_date: str, records: List[Dict[str, Any]], concepts_taught: List[str]) -> None:
        with self._lock:
            data = self.read()
            students = [Student.from_dict(item) for item in data["students"]]
            by_id = {student.id: student for student in students}
            for record in records:
                student_id = record["student_id"]
                if student_id not in by_id:
                    raise ValueError(f"unknown student: {student_id}")
                present = record["present"]
                if not isinstance(present, bool):
                    raise ValueError("attendance present must be true or false")
                student = by_id[student_id]
                student.attendance_history = [entry for entry in student.attendance_history if entry.date != attendance_date]
                student.attendance_history.append(AttendanceEntry(attendance_date, present, list(concepts_taught)))
                student.attendance_history.sort(key=lambda entry: entry.date)
                if not present:
                    for competency_id in concepts_taught:
                        if competency_id not in student.missed_concepts:
                            student.missed_concepts.append(competency_id)
            data["students"] = [student.to_dict() for student in students]
            data["attendance"] = [entry for entry in data["attendance"] if entry.get("date") != attendance_date]
            data["attendance"].append({"date": attendance_date, "records": records, "concepts_taught": concepts_taught})
            self.write(data)

    def save_groups(self, groups: List[Dict[str, Any]], reason: str = "generated") -> None:
        with self._lock:
            data = self.read()
            data["groups"] = groups
            if reason == "teacher_override":
                data["teacher_edits"].append({"type": "group_override", "at": _now(), "groups": groups})
            lookup = {student_id: group["id"] for group in groups for student_id in group["student_ids"]}
            for student in data["students"]:
                student["current_group"] = lookup.get(student["id"])
            self.write(data)

    def save_plan(self, plan: Dict[str, Any]) -> None:
        with self._lock:
            data = self.read()
            data["plans"].append(plan)
            self.write(data)

    def latest_plan(self) -> Optional[Dict[str, Any]]:
        plans = self.read().get("plans", [])
        return plans[-1] if plans else None

    def replace_latest_plan(self, plan: Dict[str, Any], edit: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            data = self.read()
            if data["plans"]:
                data["plans"][-1] = plan
            else:
                data["plans"].append(plan)
            if edit:
                data["teacher_edits"].append(dict(edit, at=_now()))
            self.write(data)

    def save_learning_evidence(
        self,
        observations: List[Dict[str, Any]],
        assessments: List[Dict[str, Any]],
        mastery_updates: List[Dict[str, Any]],
    ) -> None:
        with self._lock:
            data = self.read()
            data["observations"].extend(observations)
            data["assessments"].extend(assessments)
            data["mastery_history"].extend(mastery_updates)
            self.write(data)

    def mark_demo(self, field: str) -> None:
        if field not in {"started_at", "completed_at"}:
            raise ValueError("invalid demo field")
        with self._lock:
            data = self.read()
            data["demo"][field] = _now()
            self.write(data)


db = Database()
