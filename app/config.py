from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    #DATABASE_URL: str = "postgresql+asyncpg://insightia:insightia+++@localhost:5432/fleet_db"
    DATABASE_URL: str = "postgresql+asyncpg://neondb_owner:npg_6zIMEboLXg8A@ep-young-bread-ai02lp21-pooler.c-4.us-east-1.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
    DATABASE_URL_SYNC: str = "postgresql://insightia:insightia+++@localhost:5432/fleet_db"

    # Security
    SECRET_KEY: str = "your-super-secret-key-change-in-production-32chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    SESSION_SECRET_KEY: str = "session-secret-key-change-in-production"

    # App
    APP_NAME: str = "FleetHQ"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()