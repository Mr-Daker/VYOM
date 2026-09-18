# Saarthi-MG — Frozen Definitions
# This file is the single source of truth for problem, solution, and target user.
# Updated as each Section 0 task is completed.

# =============================================================================
# 0.1  PROBLEM STATEMENT
# =============================================================================
#
# One teacher in a multigrade classroom must teach children with different
# grades, learning levels, languages, and attendance histories, but has too
# little time to identify who needs help, what each group should do, and how
# absent or struggling students can catch up.
#
# Verification (all must be True):
#   ✅  Mentions one teacher / multiple grades or levels   → "One teacher in a multigrade classroom"
#   ✅  Mentions limited teacher time/attention             → "too little time"
#   ✅  Mentions different learning levels                  → "different grades, learning levels"
#   ✅  Mentions attendance or missed-learning gaps         → "attendance histories … absent or struggling students can catch up"
#   ✅  Explainable to a judge in under 20 seconds          → 39 words, one sentence
#
# Status: FROZEN ✅
# =============================================================================

PROBLEM_STATEMENT = (
    "One teacher in a multigrade classroom must teach children with different "
    "grades, learning levels, languages, and attendance histories, but has too "
    "little time to identify who needs help, what each group should do, and how "
    "absent or struggling students can catch up."
)

# =============================================================================
# 0.2  SOLUTION STATEMENT
# =============================================================================
#
# An AI classroom orchestrator that tracks what each child currently knows,
# groups students by learning need, decides who needs the teacher now, assigns
# meaningful activities to everyone else, and updates the next class plan using
# attendance and quick learning checks.
#
# Verification (all must be True):
#   ✅  Not a generic chatbot         → no "chat", no "ask me anything"; it orchestrates a workflow
#   ✅  Not only a lesson-plan gen     → includes grouping, scheduling, assessment, regrouping
#   ✅  Full loop present:
#        tracking   → "tracks what each child currently knows"
#        grouping   → "groups students by learning need"
#        scheduling → "decides who needs the teacher now"
#        activity   → "assigns meaningful activities to everyone else"
#        assessment → "quick learning checks"
#        regrouping → "updates the next class plan"
#   ✅  Teacher in control             → "decides who needs the teacher now" (teacher is the actor)
#
# Status: FROZEN ✅
# =============================================================================

SOLUTION_STATEMENT = (
    "An AI classroom orchestrator that tracks what each child currently knows, "
    "groups students by learning need, decides who needs the teacher now, assigns "
    "meaningful activities to everyone else, and updates the next class plan using "
    "attendance and quick learning checks."
)

# =============================================================================
# 0.3  TARGET USER
# =============================================================================
#
# Primary user:   Grades 1–3 teacher in a multigrade / multilevel classroom.
#                  The entire MVP is designed for ONE teacher device (phone or
#                  laptop). Outputs (station cards, exit tickets) are printable
#                  so no child needs a device.
#
# Secondary user: Academic coordinator / mentor / school leader who reviews
#                  plans or coaches teachers.
#
# Student:        The BENEFICIARY, not the app user. No feature requires
#                  every child to own a phone or tablet.
#
# Verification:
#   ✅  One primary user selected             → "Grades 1–3 teacher"
#   ✅  MVP designed around one teacher device → explicit constraint above
#   ✅  No child device required              → "no child needs a device"
#
# Status: FROZEN ✅
# =============================================================================

PRIMARY_USER = "Grades 1-3 teacher in a multigrade / multilevel classroom"
SECONDARY_USER = "Academic coordinator / mentor / school leader"
STUDENT_ROLE = "Beneficiary (not the app user)"
DEVICE_CONSTRAINT = "One teacher device only; outputs are printable; no child device required"

# =============================================================================
# 0.4  DEMO SCENARIO
# =============================================================================
#
# 35 students | Grades 1, 2, 3 | Hindi + Tamil | 45-min class
# 5-day attendance history | 12 competencies (7 Numeracy + 5 Reading)
# Edge cases: Rajkumar (absent), Pooja (struggling), Vihaan (advanced)
#
# Status: FROZEN ✅
# =============================================================================

DEMO_SCENARIO_FILE = "demo_scenario.json"

# =============================================================================
# 1.1  CLASSROOM LOOP (frozen workflow)
# =============================================================================
#
# Attendance → Current mastery → Detect gaps → Create groups →
# Teacher priority → Build rotation → Generate activities →
# Teacher review → Run class → Exit check → Update mastery → Regroup
#
# Every feature must map to one of these steps.
# See backend/models.py LoopStep enum for the code representation.
#
# Status: FROZEN ✅
# =============================================================================

CLASSROOM_LOOP = [
    "Attendance",
    "Current student mastery",
    "Detect learning gaps",
    "Create flexible groups",
    "Decide teacher-attention priority",
    "Build classroom rotation",
    "Generate group activities",
    "Teacher reviews/edits",
    "Run class",
    "Quick exit check",
    "Update mastery",
    "Regroup for next class",
]
