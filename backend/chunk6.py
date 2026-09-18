import os

with open("docker-compose.yml", "w") as f:
    f.write("""services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: saarthi
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d saarthi"]
      interval: 5s
      timeout: 5s
      retries: 5
      
  db_test:
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: saarthi_test
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d saarthi_test"]
      interval: 5s
      timeout: 5s
      retries: 5
  
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/saarthi
      - APP_ENV=development
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app

volumes:
  postgres_data:
""")

with open("tests/test_api.py", "w") as f:
    f.write("""import pytest
from uuid import uuid4
from app.models.all_models import User, Classroom, Student, Competency, StudentMastery, ClassSession, MasteryEvidence
from app.models.enums import UserRole, MasteryState, AttendanceStatus, SessionStatus, EvidenceSource
import uuid

def create_teacher_and_class(db_session):
    t = User(name="T", email=f"{uuid.uuid4()}@t.com", password_hash="h", role=UserRole.TEACHER)
    db_session.add(t)
    db_session.commit()
    c = Classroom(teacher_id=t.id, name="Math", default_duration_minutes=45, max_groups=4)
    db_session.add(c)
    db_session.commit()
    return t, c

def test_health(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200

def test_classroom_create(client, db_session):
    t = User(name="T", email=f"{uuid.uuid4()}@t.com", password_hash="h", role=UserRole.TEACHER)
    db_session.add(t)
    db_session.commit()
    res = client.post("/api/v1/classrooms", json={"name": "Science", "teacher_id": str(t.id), "default_duration_minutes": 45, "max_groups": 4})
    assert res.status_code == 200

def test_missing_teacher_rejected(client):
    res = client.post("/api/v1/classrooms", json={"name": "Science", "teacher_id": str(uuid.uuid4())})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"

def test_update_classroom(client, db_session):
    t, c = create_teacher_and_class(db_session)
    res = client.patch(f"/api/v1/classrooms/{c.id}", json={"name": "New Math"})
    assert res.status_code == 200
    assert res.json()["name"] == "New Math"

def test_student_valid_create(client, db_session):
    _, c = create_teacher_and_class(db_session)
    res = client.post(f"/api/v1/classrooms/{c.id}/students", json={"name": "Raj", "grade": 2})
    assert res.status_code == 200

def test_student_invalid_grade_0(client, db_session):
    _, c = create_teacher_and_class(db_session)
    res = client.post(f"/api/v1/classrooms/{c.id}/students", json={"name": "Raj", "grade": 0})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

def test_student_invalid_grade_4(client, db_session):
    _, c = create_teacher_and_class(db_session)
    res = client.post(f"/api/v1/classrooms/{c.id}/students", json={"name": "Raj", "grade": 4})
    assert res.status_code == 422

def test_student_missing_classroom(client):
    res = client.post(f"/api/v1/classrooms/{uuid.uuid4()}/students", json={"name": "Raj", "grade": 2})
    assert res.status_code == 404

def test_student_bulk_35(client, db_session):
    _, c = create_teacher_and_class(db_session)
    students = [{"name": f"S{i}", "grade": 2} for i in range(35)]
    res = client.post(f"/api/v1/classrooms/{c.id}/students/bulk", json={"students": students})
    assert res.status_code == 200
    assert len(res.json()) == 35

def test_student_atomic_invalid_bulk(client, db_session):
    _, c = create_teacher_and_class(db_session)
    students = [{"name": f"S{i}", "grade": 2} for i in range(5)]
    students.append({"name": "Bad", "grade": 4}) # invalid
    res = client.post(f"/api/v1/classrooms/{c.id}/students/bulk", json={"students": students})
    assert res.status_code == 422
    assert db_session.query(Student).count() == 0

def test_competency_valid(client):
    res = client.post("/api/v1/competencies", json={"code": f"C{uuid.uuid4()}", "subject": "math", "grade": 1, "name": "C1"})
    assert res.status_code == 200

def test_competency_duplicate_code(client):
    c_code = f"C{uuid.uuid4()}"
    client.post("/api/v1/competencies", json={"code": c_code, "subject": "math", "grade": 1, "name": "C1"})
    res = client.post("/api/v1/competencies", json={"code": c_code, "subject": "math", "grade": 1, "name": "C1"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CONFLICT"

def test_competency_missing_prereq(client, db_session):
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="C1")
    db_session.add(comp)
    db_session.commit()
    res = client.post(f"/api/v1/competencies/{comp.id}/prerequisites", json={"prerequisite_competency_id": str(uuid.uuid4())})
    assert res.status_code == 404

def test_mastery_valid(client, db_session):
    _, c = create_teacher_and_class(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N1")
    db_session.add(comp)
    db_session.commit()

    res = client.post(f"/api/v1/students/{s.id}/mastery", json={
        "competency_id": str(comp.id),
        "score": 0.5,
        "state": "developing"
    })
    assert res.status_code == 200

def test_mastery_score_below_0(client, db_session):
    _, c = create_teacher_and_class(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N1")
    db_session.add(comp)
    db_session.commit()
    res = client.post(f"/api/v1/students/{s.id}/mastery", json={"competency_id": str(comp.id), "score": -0.1, "state": "developing"})
    assert res.status_code == 422

def test_mastery_score_above_1(client, db_session):
    _, c = create_teacher_and_class(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add(s)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N1")
    db_session.add(comp)
    db_session.commit()
    res = client.post(f"/api/v1/students/{s.id}/mastery", json={"competency_id": str(comp.id), "score": 1.1, "state": "developing"})
    assert res.status_code == 422

def test_mastery_invalid_state(client, db_session):
    _, c = create_teacher_and_class(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N1")
    db_session.add_all([s, comp])
    db_session.commit()
    res = client.post(f"/api/v1/students/{s.id}/mastery", json={"competency_id": str(comp.id), "score": 0.5, "state": "invalid_state"})
    assert res.status_code == 422

def test_mastery_upsert_last_updated(client, db_session):
    _, c = create_teacher_and_class(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N1")
    db_session.add_all([s, comp])
    db_session.commit()

    res1 = client.post(f"/api/v1/students/{s.id}/mastery", json={"competency_id": str(comp.id), "score": 0.5, "state": "developing"})
    m1 = db_session.query(StudentMastery).filter_by(id=res1.json()["id"]).first()
    lu1 = m1.last_updated
    
    # Needs a tiny delay for timestamp diff
    import time
    time.sleep(0.01)

    res2 = client.post(f"/api/v1/students/{s.id}/mastery", json={"competency_id": str(comp.id), "score": 0.8, "state": "mastered"})
    db_session.refresh(m1)
    lu2 = m1.last_updated
    assert lu1 != lu2

def test_session_create(client, db_session):
    _, c = create_teacher_and_class(db_session)
    res = client.post(f"/api/v1/classrooms/{c.id}/sessions", json={"duration_minutes": 45})
    assert res.status_code == 200
    
def test_session_missing_target(client, db_session):
    _, c = create_teacher_and_class(db_session)
    res = client.post(f"/api/v1/classrooms/{c.id}/sessions", json={"duration_minutes": 45, "target_competency_id": str(uuid.uuid4())})
    assert res.status_code == 404

def test_session_duration_0(client, db_session):
    _, c = create_teacher_and_class(db_session)
    res = client.post(f"/api/v1/classrooms/{c.id}/sessions", json={"duration_minutes": 0})
    assert res.status_code == 422

def test_session_patch(client, db_session):
    _, c = create_teacher_and_class(db_session)
    sess = ClassSession(classroom_id=c.id, duration_minutes=45, status=SessionStatus.DRAFT)
    db_session.add(sess)
    db_session.commit()
    
    res = client.patch(f"/api/v1/sessions/{sess.id}", json={
        "subject": "science",
        "duration_minutes": 60,
        "status": "completed",
        "available_materials": ["book"]
    })
    assert res.status_code == 200
    assert res.json()["subject"] == "science"
    assert res.json()["status"] == "completed"

def test_attendance_foreign_classroom(client, db_session):
    t1, c1 = create_teacher_and_class(db_session)
    t2, c2 = create_teacher_and_class(db_session)
    
    s = Student(classroom_id=c1.id, name="S", grade=1)
    db_session.add(s)
    db_session.commit()
    
    sess = client.post(f"/api/v1/classrooms/{c2.id}/sessions", json={"duration_minutes": 45}).json()
    
    res = client.post(f"/api/v1/sessions/{sess['id']}/attendance", json={
        "records": [{"student_id": str(s.id), "status": "present"}]
    })
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"

def test_attendance_duplicate_in_request(client, db_session):
    _, c = create_teacher_and_class(db_session)
    s = Student(classroom_id=c.id, name="S", grade=1)
    sess = ClassSession(classroom_id=c.id, duration_minutes=45)
    db_session.add_all([s, sess])
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/attendance", json={
        "records": [
            {"student_id": str(s.id), "status": "present"},
            {"student_id": str(s.id), "status": "absent"}
        ]
    })
    assert res.status_code == 400
    assert res.json()["error"]["message"] == "Duplicate student_id found in request"
""")

with open("tests/test_seed.py", "w") as f:
    f.write("""import pytest
from app.db.session import SessionLocal
from app.models.all_models import Student, ClassSession, Competency, AttendanceRecord, StudentMastery, MasteryEvidence
from app.db.seed import run_seed

def test_seed_verification():
    # 1. We must run the seed inside the test to avoid skipping
    run_seed()
    
    db = SessionLocal()
    students = db.query(Student).all()
        
    assert len(students) == 35
    grades = [s.grade for s in students]
    assert 1 in grades and 2 in grades and 3 in grades
    
    rajkumar = db.query(Student).filter(Student.name == "Rajkumar").first()
    assert rajkumar is not None
    assert rajkumar.grade == 2

    # Verify competencies
    comps = db.query(Competency).all()
    assert len(comps) >= 8

    # Verify prerequisite chain NUM_ADD_2D -> NUM_SUB_2D
    c_add = db.query(Competency).filter(Competency.code == "NUM_ADD_2D").first()
    c_sub = db.query(Competency).filter(Competency.code == "NUM_SUB_2D").first()
    
    # Check mastery
    rm = db.query(StudentMastery).filter(StudentMastery.student_id == rajkumar.id, StudentMastery.competency_id == c_add.id).first()
    assert rm is not None
    assert rm.score == 0.48

    # Check history
    atts = db.query(AttendanceRecord).filter(AttendanceRecord.student_id == rajkumar.id).join(ClassSession).order_by(ClassSession.date).all()
    assert len(atts) >= 4
    
    assert atts[-4].status.value == "present"  # Monday
    assert atts[-3].status.value == "absent"   # Tuesday
    assert atts[-2].status.value == "absent"   # Wednesday
    assert atts[-1].status.value == "present"  # Thursday

    # Verify target competencies on those sessions
    sessions = db.query(ClassSession).filter(ClassSession.classroom_id == rajkumar.classroom_id).order_by(ClassSession.date).all()
    assert sessions[-4].target_competency_id == c_add.id
    assert sessions[-1].target_competency_id == c_sub.id

    # Verify varied attendance exists (at least one late, one absent somewhere else)
    all_atts = db.query(AttendanceRecord).filter(AttendanceRecord.student_id != rajkumar.id).all()
    statuses = set([a.status.value for a in all_atts])
    assert "late" in statuses
    assert "absent" in statuses

    # Varied mastery states
    all_mastery = db.query(StudentMastery).all()
    states = set([m.state.value for m in all_mastery])
    assert "unknown" in states
    assert "needs_support" in states
    assert "mastered" in states

    # Meaningful evidence
    evs = db.query(MasteryEvidence).all()
    assert len(evs) > 0
    ev_sources = set([e.source_type.value for e in evs])
    assert len(ev_sources) > 1

    # Idempotency check
    run_seed()
    students_after = db.query(Student).all()
    assert len(students_after) == 35 # Should not duplicate
""")

with open("tests/test_db_constraints.py", "w") as f:
    f.write("""import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError, DataError, ProgrammingError
from app.models.all_models import Base, StudentMastery, Student, Classroom, Competency, User, CompetencyPrerequisite, ClassSession, MasteryEvidence, AttendanceRecord
from app.models.enums import UserRole, MasteryState, EvidenceSource, AttendanceStatus, SessionStatus
import uuid

# These tests directly bind to PostgreSQL to verify actual native checks.
# If testing against sqlite, some check constraints might pass silently or throw different errors.
DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@db_test:5432/saarthi_test")

@pytest.fixture(scope="module")
def pg_session():
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_db_mastery_duplicate(pg_session):
    u = User(name="T", email=f"{uuid.uuid4()}@t", password_hash="h", role=UserRole.TEACHER)
    pg_session.add(u)
    pg_session.flush()
    c = Classroom(teacher_id=u.id, name="C", default_duration_minutes=45, max_groups=2)
    pg_session.add(c)
    pg_session.flush()
    s = Student(classroom_id=c.id, name="S", grade=1)
    pg_session.add(s)
    comp = Competency(code=f"C{uuid.uuid4()}", subject="math", name="N", grade=1)
    pg_session.add(comp)
    pg_session.commit()

    m1 = StudentMastery(student_id=s.id, competency_id=comp.id, score=0.5, state=MasteryState.DEVELOPING)
    pg_session.add(m1)
    pg_session.commit()

    m2 = StudentMastery(student_id=s.id, competency_id=comp.id, score=0.6, state=MasteryState.DEVELOPING)
    pg_session.add(m2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_mastery_score_bounds(pg_session):
    s = pg_session.query(Student).first()
    comp = pg_session.query(Competency).first()
    
    m = StudentMastery(student_id=s.id, competency_id=comp.id, score=1.5, state=MasteryState.DEVELOPING)
    pg_session.add(m)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_evidence_score_bounds(pg_session):
    s = pg_session.query(Student).first()
    comp = pg_session.query(Competency).first()
    
    e = MasteryEvidence(student_id=s.id, competency_id=comp.id, source_type=EvidenceSource.MANUAL_ASSESSMENT, score=-0.1)
    pg_session.add(e)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_student_invalid_grade(pg_session):
    c = pg_session.query(Classroom).first()
    s = Student(classroom_id=c.id, name="Bad", grade=4)
    pg_session.add(s)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_self_prerequisite(pg_session):
    comp = pg_session.query(Competency).first()
    p = CompetencyPrerequisite(competency_id=comp.id, prerequisite_competency_id=comp.id)
    pg_session.add(p)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_db_duplicate_attendance(pg_session):
    c = pg_session.query(Classroom).first()
    s = pg_session.query(Student).first()
    sess = ClassSession(classroom_id=c.id, duration_minutes=45, status=SessionStatus.DRAFT)
    pg_session.add(sess)
    pg_session.commit()

    a1 = AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT)
    pg_session.add(a1)
    pg_session.commit()

    a2 = AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.ABSENT)
    pg_session.add(a2)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

def test_session_poison_recovery(pg_session):
    # If a commit fails with IntegrityError, the session should be usable after rollback
    c = pg_session.query(Classroom).first()
    
    # Try bad grade
    s = Student(classroom_id=c.id, name="Bad", grade=5)
    pg_session.add(s)
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()
    
    # Session is unpoisoned, can insert good row
    s_good = Student(classroom_id=c.id, name="Good", grade=2)
    pg_session.add(s_good)
    pg_session.commit()
    assert s_good.id is not None
""")
