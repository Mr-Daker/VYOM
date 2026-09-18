import os

class Settings:
    MASTERY_STALE_DAYS: int = int(os.getenv("MASTERY_STALE_DAYS", "30"))
    GAP_ATTENDANCE_LOOKBACK_DAYS: int = int(os.getenv("GAP_ATTENDANCE_LOOKBACK_DAYS", "30"))
    
settings = Settings()
