# Backend Specification — Multigrade Classroom Orchestrator

## 1. Backend Goal
The backend must solve this complete loop:
Student data -> Attendance -> Current mastery -> Detect learning gaps -> Group students by learning need -> Determine who needs teacher attention first -> Generate classroom rotation -> Retrieve trusted curriculum -> Generate level-specific activities -> Validate AI output -> Teacher approves plan -> Class happens -> Exit ticket + teacher observations -> Update mastery -> Regroup for next class

The backend is **not just CRUD + an LLM API**. Its core intelligence is Gap Detection -> Grouping -> Teacher Priority -> Scheduling -> Activity Generation -> Assessment -> Mastery Update.

## 2. Recommended Backend Stack
- Core: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, pgvector, pytest
- AI: Claude API, PostgreSQL + pgvector (RAG), IndicTrans2 / LLM (Translation)
- Deployment: Docker, Docker Compose
- *Do not add Redis, Kafka, Celery, Kubernetes, microservices.*

## 3. High-Level Backend Architecture
FastAPI REST API -> Classroom/Orchestration/Curriculum Services -> Gap/Group/Priority/Scheduler -> Activity Service (RAG+LLM -> Validators) -> Assessment Service -> Mastery Service -> PostgreSQL.

## 4. Main Backend Modules
Authentication, Classroom Management, Student Management, Attendance, Competency Management, Mastery Tracking, Learning Gap Detection, Student Grouping, Teacher Attention Prioritization, Rotation Scheduling, Curriculum Knowledge Base, RAG, Activity Generation, Activity Validation, Multilingual Adaptation, Exit Tickets, Teacher Observations, Mastery Updating, Next-Class Regrouping, Analytics/Evaluation, Audit/Explainability.

## 5. Database Model (High Level)
- **User**: id, name, email, role (teacher, admin)
- **Classroom**: default_language, max_groups, default_duration_minutes
- **Student**: name, grade, preferred_language, active. (No religion/caste/biometric data).
- **Competency**: code, subject, grade, name.
- **CompetencyPrerequisite**: competency_id, prerequisite_competency_id (Crucial for the Rajkumar use case).
- **StudentMastery**: score, state (needs_support, developing, mastered, unknown), confidence. (Thresholds: 0-0.39, 0.40-0.69, 0.70-1.00).
- **MasteryEvidence**: source_type, score. (Never overwrite evidence).
- **AttendanceRecord**: present, absent, late. (Absence does NOT automatically decrease mastery, it flags a possible missed-learning gap).
- **ClassSession**: statuses (draft, grouped, scheduled, in_progress, completed, etc.).
- **LearningGroup**: reason, mastery_level, target_competency.
- **GroupMembership**: group_id, student_id.

## Intelligence Engines
- **Gap Detection**: Confirmed gap, possible gap, insufficient evidence. Considers prerequisites and absence.
- **Grouping Engine**: Based on learning need, not just grade. Interpretable rules (no K-means). Constraints: Every present student in 1 group, no absent students, respects max_groups.
- **Teacher Priority Engine**: Priority = prerequisite_gap (0.30) + learning_need (0.25) + absence_recovery (0.15) + prerequisite_importance (0.15) + support_staleness (0.10) + teacher_override (0.05). Must return explainable reasons.
- **Rotation Scheduler**: No teacher conflicts, everyone has an activity, fits duration, priority dictates teacher time.

## Curriculum & AI
- **Curriculum KB / RAG**: Return chunks. Do NOT silently generate unsupported material if confidence is poor.
- **Activity Model**: teacher_led, guided_practice, peer_activity, independent, manipulative, recovery, extension.
- **LLM Input**: Structured. NO STUDENT NAMES SENT TO LLM (Privacy).
- **LLM Output Schema**: Enforced JSON (title, objective, instructions, materials, quick_check, source_reference).
- **Activity Validator**: Schema, Competency, Duration, Material, Difficulty, Curriculum Grounding, Safety.
- **AI Fallback**: Validation pass -> Retry once -> Curated baseline template -> Graceful warning. Never crash.
- **Translation**: Configurable, do not translate IDs/math.

## Assessment & Feedback
- **Exit Tickets**: 1-2 minutes long, small assessment.
- **Teacher Observation**: Lightweight (understood, needs_practice, not_assessed).
- **Mastery Update Engine**: Deterministic rules for MVP. (e.g. correct +0.15, understood +0.10, incorrect -0.05). Clamp 0-1.
- **Next-Class Regrouping**: Closes the loop based on new mastery evidence.

## Privacy & Ethics
- No student names to LLM.
- Aggregate group info before AI calls.
- Teacher is final decision maker.
- Never infer intelligence or ability labels ("needs support on addition" not "slow learner").

## Development Phases
- **Phase 1**: Data foundation (DB, models, seed)
- **Phase 2**: Core intelligence (Gap, Group, Priority, Scheduler - NO LLM)
- **Phase 3**: Curriculum + AI (RAG, LLM, Validators)
- **Phase 4**: Learning feedback (Exit tickets, Observations, Mastery update, Regrouping)
- **Phase 5**: Backend polish (Auth, Analytics, Docker, Tests)

## Rajkumar Integration Test (The Ultimate End-to-End Test)
- Grade 2, Addition mastery 0.48. Absent Tue/Wed. Present Mon/Thu. Target: Subtraction.
- Backend detects addition prerequisite gap -> Assigns to Addition Recovery -> High Priority -> Scheduler gives teacher time -> Generates grounded addition activity -> Teacher approves -> Exit ticket correct -> Teacher marks understood -> Mastery 0.48 to 0.73 (Mastered) -> Recommended group: Developing Subtraction.
