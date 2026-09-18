import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from api import ApiRouter, _activity_from_dict
from db import Database
from engines import build_groups, build_rotation_schedule, prioritize_groups
from gap_engine import detect_gaps
from generator import generate_activity, validate_activity
from models import ActivityType, CompetencyRecord, MasteryState, Student


def demo_students():
    with open(os.path.join(ROOT, "demo_scenario.json"), encoding="utf-8") as handle:
        return [Student.from_dict(item) for item in json.load(handle)["students"]]


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.students = demo_students()

    def test_demo_is_mixed_grade_and_has_edge_cases(self):
        self.assertEqual(len(self.students), 35)
        self.assertEqual({student.grade for student in self.students}, {1, 2, 3})
        self.assertIn("STU020", {student.id for student in self.students})
        self.assertIn("STU027", {student.id for student in self.students})

    def test_malformed_mastery_is_rejected(self):
        with self.assertRaises(ValueError):
            CompetencyRecord.from_dict({"competency_id": "N1", "score": 1.2, "state": "Mastered"})
        with self.assertRaises(ValueError):
            Student.from_dict({"id": "A", "name": "A", "grade": 7, "home_language": "Hindi"})

    def test_gap_engine_handles_rajkumar_and_advanced_learner(self):
        rajkumar = next(student for student in self.students if student.id == "STU020")
        vihaan = next(student for student in self.students if student.id == "STU027")
        raj = detect_gaps(rajkumar, "N6", "2026-09-11")
        advanced = detect_gaps(vihaan, "N6", "2026-09-11")
        self.assertEqual(raj["focus_competency_id"], "N4")
        self.assertEqual(raj["recovery_need"], "High")
        self.assertTrue(raj["returning_after_absence"])
        self.assertEqual(advanced["missing_prerequisites"], [])
        self.assertEqual(advanced["recovery_need"], "Low")

    def test_grouping_respects_max_and_assigns_once(self):
        for maximum in (2, 3, 4):
            groups = build_groups(self.students, "N6", "2026-09-11", maximum)
            assigned = [student_id for group in groups for student_id in group.student_ids]
            self.assertLessEqual(len(groups), maximum)
            self.assertEqual(sorted(assigned), sorted(student.id for student in self.students))
            self.assertEqual(len(assigned), len(set(assigned)))

    def test_priority_and_schedule_invariants(self):
        groups = prioritize_groups(build_groups(self.students, "N6", "2026-09-11", 4), self.students, "2026-09-11")
        raj_group = next(group for group in groups if "STU020" in group.student_ids)
        self.assertEqual(groups[0].id, raj_group.id)
        self.assertIn("prerequisite_gap", groups[0].priority_factors)
        schedule = build_rotation_schedule(groups, 45, 15, ["paper", "pencils", "chalk", "blackboard", "bottle caps"], "English")
        self.assertEqual(len(schedule), len(groups) * 3)
        for index in range(3):
            slot = [item for item in schedule if item.slot_index == index]
            self.assertEqual(len(slot), len(groups))
            self.assertEqual(sum(item.activity.teacher_involvement_required for item in slot), 1)
            self.assertEqual({item.end_minute - item.start_minute for item in slot}, {15})

    def test_grounded_generation_is_valid_and_bilingual(self):
        materials = ["paper", "pencils", "chalk", "blackboard", "bottle caps"]
        ids = set()
        for language in ("English", "Hindi"):
            for variation in range(10):
                activity = generate_activity("N4", "Developing", 15, language, materials, ActivityType.PEER_ACTIVITY, "G1", variation=variation)
                self.assertEqual(validate_activity(activity, materials, 15), [])
                self.assertEqual(activity.competency_id, "N4")
                self.assertTrue(activity.source_reference)
                ids.add(activity.id)
        self.assertGreaterEqual(len(ids), 6)

    def test_manual_baseline_library_matches_the_activity_contract(self):
        with open(os.path.join(ROOT, "data", "baseline_activities.json"), encoding="utf-8") as handle:
            raw_activities = json.load(handle)
        self.assertGreaterEqual(len(raw_activities), 10)
        available = ["paper", "pencils", "chalk", "blackboard", "bottle caps", "sticks (bundles of 10)", "number cards (1-100)"]
        for item in raw_activities:
            activity = _activity_from_dict(item)
            self.assertEqual(validate_activity(activity, available, activity.duration_minutes), [])


class ApiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Database(os.path.join(self.tempdir.name, "database.json"), os.path.join(ROOT, "demo_scenario.json"))
        self.router = ApiRouter(self.database)

    def tearDown(self):
        self.tempdir.cleanup()

    def attendance_payload(self):
        students = self.router.get_bootstrap()["students"]
        return {
            "date": "2026-09-11",
            "concepts_taught": ["N6"],
            "records": [{"student_id": item["id"], "present": True} for item in students],
        }

    def build_to_plan(self):
        self.router.post_attendance(self.attendance_payload())
        groups = self.router.post_groups_generate({})["groups"]
        plan = self.router.post_schedule_generate({})["plan"]
        return groups, plan

    def test_complete_rajkumar_story_and_persistence(self):
        groups, plan = self.build_to_plan()
        self.assertLessEqual(len(groups), 4)
        raj_before = next(group for group in groups if "STU020" in group["student_ids"])
        self.assertEqual(raj_before["focus_competency_id"], "N4")
        self.assertEqual(raj_before["mastery_level"], "RECOVERY")
        self.assertEqual(len({slot["activity"]["id"] for slot in plan["schedule"]}), len(plan["schedule"]))

        approved = self.router.post_plan_approval(plan["id"], {"approved": True})
        self.assertTrue(approved["plan"]["teacher_approved"])
        result = self.router.post_next_plan({
            "date": "2026-09-11",
            "evidence": [{"student_id": "STU020", "competency_id": "N4", "observation": "understood", "exit_ticket_correct": True}],
        })
        update = next(item for item in result["updates"] if item["student_id"] == "STU020")
        raj_after = next(group for group in result["groups"] if "STU020" in group["student_ids"])
        self.assertEqual(update["new_state"], "Mastered")
        self.assertNotEqual(raj_after["mastery_level"], "RECOVERY")
        self.assertTrue(any(item["student_id"] == "STU020" for item in result["movements"]))

        reloaded = Database(self.database.path, self.database.demo_path)
        saved_raj = next(student for student in reloaded.get_students() if student.id == "STU020")
        self.assertEqual(saved_raj.competencies["N4"].state, MasteryState.MASTERED)
        snapshot = reloaded.read()
        self.assertTrue(snapshot["mastery_history"])
        self.assertTrue(snapshot["assessments"])

    def test_teacher_can_override_edit_reject_and_regenerate(self):
        groups, plan = self.build_to_plan()
        override = self.router.post_groups_override({"groups": [{"id": group["id"], "student_ids": group["student_ids"]} for group in groups]})
        self.assertEqual(len(override["groups"]), len(groups))
        activity = plan["schedule"][0]["activity"]
        edited = self.router.post_activity_update(activity["id"], {"title": "Teacher-adjusted recovery", "status": "draft"})
        self.assertEqual(edited["activity"]["generated_by"], "teacher-edited")
        rejected = self.router.post_activity_update(activity["id"], {"status": "rejected"})
        self.assertEqual(rejected["activity"]["status"], "rejected")
        with self.assertRaises(ValueError):
            self.router.post_plan_approval(plan["id"], {"approved": True})
        regenerated = self.router.post_activity_regenerate(activity["id"], {"variation": 2})
        self.assertNotEqual(regenerated["activity"]["id"], activity["id"])
        self.assertEqual(self.router.post_plan_approval(plan["id"], {"approved": True})["status"], "approved")

    def test_all_core_service_endpoints(self):
        self.router.post_classrooms({"instruction_language": "Hindi", "class_duration_minutes": 30, "slot_duration_minutes": 10})
        self.router.post_attendance(self.attendance_payload())
        groups = self.router.post_groups_generate({})["groups"]
        self.assertTrue(groups)
        self.assertIn("gap_report", self.router.get_student_mastery("STU020"))
        plan = self.router.post_schedule_generate({})["plan"]
        self.assertTrue(plan["exit_tickets"])
        generated = self.router.post_activities_generate({"competency_id": "N4", "group_id": "G1", "language": "Hindi"})
        self.assertIn("activity", generated)
        self.assertIn("exit_ticket", self.router.post_exit_ticket({"competency_id": "N4", "group_id": "G1", "language": "Hindi"}))
        self.assertEqual(self.router.post_observations({"observations": [{"student_id": "STU020", "competency_id": "N4", "observation": "understood"}]})["count"], 1)
        self.assertEqual(self.router.post_mastery_update({"student_id": "STU020", "competency_id": "N4", "exit_ticket_correct": True, "observation": "understood"})["status"], "updated")


class EvaluationTests(unittest.TestCase):
    def test_fixed_benchmark_results_exist(self):
        with open(os.path.join(ROOT, "evaluation", "benchmark_scenarios.json"), encoding="utf-8") as handle:
            scenarios = json.load(handle)
        with open(os.path.join(ROOT, "evaluation", "results.json"), encoding="utf-8") as handle:
            results = json.load(handle)
        self.assertEqual(len(scenarios), 30)
        self.assertEqual(results["scenario_count"], 30)
        self.assertEqual(results["summary"]["grouping"]["constraint_violations"], 0)
        self.assertEqual(results["summary"]["scheduling"]["teacher_conflicts"], 0)
        self.assertIn("not a teacher study", results["scope_note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
