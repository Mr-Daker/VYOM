import pytest
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
    m1 = db_session.query(StudentMastery).filter_by(id=uuid.UUID(res1.json()["id"])).first()
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
