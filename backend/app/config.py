from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # TimeStation
    TIMESTATION_API_KEY: str = ""
    TIMESTATION_API_BASE: str = "https://api.mytimestation.com/v1.2"

    # Auth
    SECRET_KEY: str = "changeme-generate-a-real-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # Database
    DATABASE_URL: str = "sqlite:///./employee_portal.db"

    # Email (Postmark)
    POSTMARK_API_KEY: str = ""
    EMAIL_FROM: str = "Allied Connect <support@alliedalliancegroupinc.com>"

    # Frontend URL (for CORS)
    FRONTEND_URL: str = "http://localhost:5173"

    # Cache TTLs (seconds)
    CACHE_TTL_EMPLOYEES: int = 300   # 5 min
    CACHE_TTL_SHIFTS: int = 900      # 15 min
    CACHE_TTL_STATUS: int = 120      # 2 min

    # Late arrival threshold (default 1 minute; overridable via Settings UI)
    LATE_THRESHOLD_MINUTES: int = 1

    # Pay dates (8th and 22nd)
    PAY_DATES: list[int] = [8, 22]

    # Document storage
    STORAGE_DIR: str = "storage/documents"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
