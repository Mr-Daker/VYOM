import os

class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/saarthi",
    )
    APP_ENV: str = os.getenv(
        "APP_ENV",
        "development",
    )
    MASTERY_STALE_DAYS: int = int(os.getenv("MASTERY_STALE_DAYS", "30"))
    GAP_ATTENDANCE_LOOKBACK_DAYS: int = int(os.getenv("GAP_ATTENDANCE_LOOKBACK_DAYS", "30"))

settings = Settings()
