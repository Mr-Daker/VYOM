from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from app.api.router import api_router
from app.core.exceptions import AppException, app_exception_handler

app = FastAPI(title="Multigrade Classroom Orchestrator")

@app.exception_handler(AppException)
async def custom_app_exception_handler(request: Request, exc: AppException):
    return app_exception_handler(request, exc)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request parameters",
                "details": [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
            }
        }
    )

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    if isinstance(exc, IntegrityError):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "CONFLICT",
                    "message": "A database conflict occurred (e.g., unique constraint violation).",
                    "details": {}
                }
            }
        )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "DATABASE_ERROR",
                "message": "An unexpected database error occurred.",
                "details": {}
            }
        }
    )

app.include_router(api_router, prefix="/api/v1")
