# config.py — single source of truth for all application configuration.
# Reads environment variables from backend/.env using pydantic-settings.
# Every other module imports `settings` from here instead of calling os.getenv() directly.

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded and validated from environment variables / .env file.

    Pydantic validates every field at startup. If a required field is missing the app
    crashes immediately with a clear error naming the missing variable — this is
    intentional so misconfigured deployments fail fast rather than silently misbehave.

    Args: none — fields are populated automatically from environment variables.
    Returns: a validated Settings instance.
    Raises: ValidationError if any required field is absent or has an invalid value.
    """

    model_config = SettingsConfigDict(
        # __file__ is the absolute path to this config.py file.
        # .parent gives the backend/ directory that contains .env.
        # This makes .env discovery independent of which directory uvicorn is run from.
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        # "ignore" means env vars not declared as fields are silently skipped.
        # Without this, any extra var in .env (e.g. for future sections) causes a startup crash.
        extra="ignore",
    )

    # --- Required fields: no default means the app WILL NOT START if these are missing ---
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    # --- Optional fields with safe defaults ---
    APP_ENV: Literal["development", "production"] = "development"
    # Literal restricts LOG_LEVEL to exactly these four values — anything else is a startup error
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    APP_VERSION: str = "0.1.0"
    # Maximum upload size in megabytes — multiplied by 1024*1024 in ingestion.py.
    # Override in .env: MAX_FILE_SIZE_MB=20
    MAX_FILE_SIZE_MB: int = 20


# Module-level singleton — Settings() is called once at startup, not once per request.
# Every other module does: from config import settings
settings = Settings()
