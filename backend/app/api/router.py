from fastapi import APIRouter
from app.api.routes import grouping
from app.api.routes import curriculum
from app.api.routes import activity
from app.api.routes import health, classrooms, students, competencies, mastery, sessions, attendance, gaps, priority, rotation

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(classrooms.router, prefix="/classrooms", tags=["classrooms"])
api_router.include_router(students.router, tags=["students"])
api_router.include_router(competencies.router, prefix="/competencies", tags=["competencies"])
api_router.include_router(mastery.router, prefix="/students", tags=["mastery"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(attendance.router, tags=["attendance"])
api_router.include_router(gaps.router, tags=["gap_detection"])

api_router.include_router(grouping.router, tags=['grouping'])

api_router.include_router(priority.router, prefix="/sessions", tags=["Priority"])
api_router.include_router(rotation.router, prefix="/sessions", tags=["Rotation"])
api_router.include_router(activity.router, prefix="/sessions", tags=["Activities"])

api_router.include_router(curriculum.router, tags=['curriculum'])
