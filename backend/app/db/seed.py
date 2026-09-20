import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db.session import SessionLocal
from app.models.all_models import User, Classroom, Student, Competency, CompetencyPrerequisite, ClassSession, AttendanceRecord, StudentMastery, MasteryEvidence
from app.models.enums import UserRole, SessionStatus, AttendanceStatus, MasteryState, EvidenceSource

def utc_now():
    return datetime.now(timezone.utc)

def run_seed(session_factory=SessionLocal):
    db = session_factory()
    
    try:
        # Idempotency: find demo teacher
        t = db.query(User).filter(User.email == "priya_demo@example.com").first()
        if t:
            # Delete associated classroom, which cascades students, sessions, mastery, evidence, attendance
            for c in t.classrooms:
                db.delete(c)
            db.commit()
        else:
            t = User(name="Priya Sharma (Demo)", email="priya_demo@example.com", password_hash="hash", role=UserRole.TEACHER)
            db.add(t)
            db.commit()

        # Re-fetch just to be sure
        t = db.query(User).filter(User.email == "priya_demo@example.com").first()

        # 2. Classroom
        c = Classroom(
            teacher_id=t.id,
            name="Demo Grades 1-3 Mathematics",
            school_name="Village Primary",
            default_language="en",
            secondary_language="ta",
            default_duration_minutes=45,
            max_groups=4
        )
        db.add(c)
        db.flush()

        # 3. Competencies (At least 8)
        comp_defs = [
            ("NUM_COUNT", "mathematics", 1, "Counting 1-100"),
            ("NUM_COMPARE", "mathematics", 1, "Comparing Numbers"),
            ("NUM_PLACE_VALUE", "mathematics", 2, "Place Value"),
            ("NUM_ADD_2D", "mathematics", 2, "Two-digit addition"),
            ("NUM_SUB_2D", "mathematics", 2, "Two-digit subtraction"),
            ("NUM_MULT_1D", "mathematics", 3, "One-digit multiplication"),
            ("GEO_SHAPES_2D", "mathematics", 1, "2D Shapes"),
            ("GEO_SHAPES_3D", "mathematics", 2, "3D Shapes"),
            ("MEAS_LENGTH", "mathematics", 1, "Measuring Length")
        ]
        
        comps = {}
        for code, sub, grd, name in comp_defs:
            comp = db.query(Competency).filter(Competency.code == code).first()
            if not comp:
                comp = Competency(code=code, subject=sub, grade=grd, name=name)
                db.add(comp)
            comps[code] = comp
        db.flush()

        # Prerequisites
        prereqs = [
            ("NUM_COUNT", "NUM_COMPARE"),
            ("NUM_COMPARE", "NUM_PLACE_VALUE"),
            ("NUM_PLACE_VALUE", "NUM_ADD_2D"),
            ("NUM_ADD_2D", "NUM_SUB_2D"),
            ("GEO_SHAPES_2D", "GEO_SHAPES_3D")
        ]
        
        for pre, target in prereqs:
            c_pre = comps[pre]
            c_tar = comps[target]
            existing_p = db.query(CompetencyPrerequisite).filter(
                CompetencyPrerequisite.competency_id == c_tar.id,
                CompetencyPrerequisite.prerequisite_competency_id == c_pre.id
            ).first()
            if not existing_p:
                db.add(CompetencyPrerequisite(competency_id=c_tar.id, prerequisite_competency_id=c_pre.id))
        db.flush()

        # 4. Students (35 Total)
        students = []
        # Rajkumar (Grade 2)
        rajkumar = Student(classroom_id=c.id, name="Rajkumar", grade=2, preferred_language="ta")
        db.add(rajkumar)
        students.append(rajkumar)

        # Aditi (Grade 2)
        aditi = Student(classroom_id=c.id, name="Aditi", grade=2, preferred_language="en")
        db.add(aditi)
        students.append(aditi)

        # Kiran (Grade 2)
        kiran = Student(classroom_id=c.id, name="Kiran", grade=2, preferred_language="ta")
        db.add(kiran)
        students.append(kiran)

        # Rest of the 32 students
        for i in range(11):
            s = Student(classroom_id=c.id, name=f"Grade1_Student_{i}", grade=1)
            db.add(s)
            students.append(s)
        for i in range(10):  # +3 above = 13 Grade 2
            s = Student(classroom_id=c.id, name=f"Grade2_Student_{i}", grade=2)
            db.add(s)
            students.append(s)
        for i in range(11):
            s = Student(classroom_id=c.id, name=f"Grade3_Student_{i}", grade=3)
            db.add(s)
            students.append(s)
        db.flush()

        # 5. Mastery and Evidence
        
        # Rajkumar (Developing Addition, ~0.48)
        db.add(StudentMastery(student_id=rajkumar.id, competency_id=comps["NUM_ADD_2D"].id, score=0.48, state=MasteryState.DEVELOPING))
        db.add(MasteryEvidence(student_id=rajkumar.id, competency_id=comps["NUM_ADD_2D"].id, source_type=EvidenceSource.INITIAL_ASSESSMENT, score=0.48))
        
        # Aditi (Advanced, Mastered sub/add)
        db.add(StudentMastery(student_id=aditi.id, competency_id=comps["NUM_ADD_2D"].id, score=0.9, state=MasteryState.MASTERED))
        db.add(StudentMastery(student_id=aditi.id, competency_id=comps["NUM_SUB_2D"].id, score=0.85, state=MasteryState.MASTERED))
        db.add(MasteryEvidence(student_id=aditi.id, competency_id=comps["NUM_ADD_2D"].id, source_type=EvidenceSource.TEACHER_OBSERVATION, score=0.92))
        
        # Kiran (Struggling, needs support with place value)
        db.add(StudentMastery(student_id=kiran.id, competency_id=comps["NUM_PLACE_VALUE"].id, score=0.2, state=MasteryState.NEEDS_SUPPORT))
        db.add(MasteryEvidence(student_id=kiran.id, competency_id=comps["NUM_PLACE_VALUE"].id, source_type=EvidenceSource.MANUAL_ASSESSMENT, score=0.2))

        # Varied Mastery for other students
        # Grade 1 students developing Counting/Comparing
        for s in students[3:8]:
            db.add(StudentMastery(student_id=s.id, competency_id=comps["NUM_COUNT"].id, score=0.6, state=MasteryState.DEVELOPING))
        # Grade 2 missing recent evidence (Unknown)
        for s in students[14:18]:
            db.add(StudentMastery(student_id=s.id, competency_id=comps["NUM_ADD_2D"].id, score=0.0, state=MasteryState.UNKNOWN))
        # Grade 3 Mastered Subtraction
        for s in students[-5:]:
            db.add(StudentMastery(student_id=s.id, competency_id=comps["NUM_SUB_2D"].id, score=0.95, state=MasteryState.MASTERED))

        db.flush()

        # 6. Historical Sessions (Monday, Tuesday, Wednesday, Thursday)
        base_time = utc_now() - timedelta(days=3)
        
        mon = ClassSession(classroom_id=c.id, date=base_time, subject="mathematics", target_competency_id=comps["NUM_ADD_2D"].id, duration_minutes=45, status=SessionStatus.COMPLETED)
        tue = ClassSession(classroom_id=c.id, date=base_time + timedelta(days=1), subject="mathematics", target_competency_id=comps["NUM_ADD_2D"].id, duration_minutes=45, status=SessionStatus.COMPLETED)
        wed = ClassSession(classroom_id=c.id, date=base_time + timedelta(days=2), subject="mathematics", target_competency_id=comps["NUM_ADD_2D"].id, duration_minutes=45, status=SessionStatus.COMPLETED)
        thu = ClassSession(classroom_id=c.id, date=base_time + timedelta(days=3), subject="mathematics", target_competency_id=comps["NUM_SUB_2D"].id, duration_minutes=45, status=SessionStatus.DRAFT)
        
        db.add_all([mon, tue, wed, thu])
        db.flush()

        # Rajkumar Attendance
        db.add(AttendanceRecord(student_id=rajkumar.id, class_session_id=mon.id, status=AttendanceStatus.PRESENT))
        db.add(AttendanceRecord(student_id=rajkumar.id, class_session_id=tue.id, status=AttendanceStatus.ABSENT))
        db.add(AttendanceRecord(student_id=rajkumar.id, class_session_id=wed.id, status=AttendanceStatus.ABSENT))
        db.add(AttendanceRecord(student_id=rajkumar.id, class_session_id=thu.id, status=AttendanceStatus.PRESENT))

        # Varied attendance for others
        for idx, s in enumerate(students):
            if s.id == rajkumar.id: continue
            
            # 1. Consistently present
            if idx % 4 == 0:
                db.add(AttendanceRecord(student_id=s.id, class_session_id=mon.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=tue.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=wed.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=thu.id, status=AttendanceStatus.PRESENT))
            # 2. One day absent (Tuesday)
            elif idx % 4 == 1:
                db.add(AttendanceRecord(student_id=s.id, class_session_id=mon.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=tue.id, status=AttendanceStatus.ABSENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=wed.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=thu.id, status=AttendanceStatus.PRESENT))
            # 3. Late
            elif idx % 4 == 2:
                db.add(AttendanceRecord(student_id=s.id, class_session_id=mon.id, status=AttendanceStatus.LATE))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=tue.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=wed.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=thu.id, status=AttendanceStatus.LATE))
            # 4. Missed different lessons
            else:
                db.add(AttendanceRecord(student_id=s.id, class_session_id=mon.id, status=AttendanceStatus.ABSENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=tue.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=wed.id, status=AttendanceStatus.PRESENT))
                db.add(AttendanceRecord(student_id=s.id, class_session_id=thu.id, status=AttendanceStatus.ABSENT))

        db.commit()
        print("Database seeded successfully with historical Rajkumar scenario and 35 varied students.")
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()
