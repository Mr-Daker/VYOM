with open("tests/test_gap_detection.py", "r") as f:
    content = f.read()

import re

new_test_34 = """# 34. Genuine cycle
def test_genuine_cycle_warning(client, db_session):
    c = setup_base(db_session)
    c_a = Competency(code=f"A{uuid.uuid4()}", subject="math", name="A")
    c_b = Competency(code=f"B{uuid.uuid4()}", subject="math", name="B")
    c_t = Competency(code=f"T{uuid.uuid4()}", subject="math", name="T")
    s = Student(classroom_id=c.id, name="S", grade=1)
    db_session.add_all([c_a, c_b, c_t, s])
    db_session.commit()
    
    # T -> A -> B -> A
    db_session.add(CompetencyPrerequisite(competency_id=c_t.id, prerequisite_competency_id=c_a.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_a.id, prerequisite_competency_id=c_b.id))
    db_session.add(CompetencyPrerequisite(competency_id=c_b.id, prerequisite_competency_id=c_a.id))
    db_session.commit()
    
    sess = ClassSession(classroom_id=c.id, target_competency_id=c_t.id, duration_minutes=45)
    db_session.add(sess)
    db_session.commit()
    db_session.add(AttendanceRecord(student_id=s.id, class_session_id=sess.id, status=AttendanceStatus.PRESENT))
    db_session.commit()
    
    res = client.post(f"/api/v1/sessions/{sess.id}/detect-gaps")
    data = res.json()
    assert len(data["metadata"]["warnings"]) > 0
    assert any("A -> B -> A" in w for w in data["metadata"]["warnings"])
"""

content = re.sub(
    r"# 34\. Genuine cycle.*?assert len\(data\[\"metadata\"\]\[\"warnings\"\]\) > 0\n",
    new_test_34,
    content,
    flags=re.DOTALL
)

with open("tests/test_gap_detection.py", "w") as f:
    f.write(content)

