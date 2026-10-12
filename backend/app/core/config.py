from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "RideWave"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Defaults to local SQLite file for zero-config local development without PostgreSQL/Docker
    DATABASE_URL: str = "sqlite+aiosqlite:///./ridewave.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Schema migration control
    AUTO_CREATE_TABLES: bool = False

    # CORS origins
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://ridewave-rosy.vercel.app",
    ]

    # AI Configuration (strictly zero-cost / local inference)
    AI_ENABLED: bool = False
    LLM_PROVIDER: str = "ollama"  # "ollama" (local) or "openrouter" (free catalog)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "meta-llama/llama-3.2-3b-instruct:free"

    # Spatial defaults
    MAX_MATCHING_RADIUS_KM: float = 5.0
    H3_RESOLUTION: int = 8

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_production_secret(cls, v: str, info) -> str:
        # If in production, prevent insecure secret defaults
        app_env = info.data.get("APP_ENV", "development")
        if app_env == "production":
            if "insecure" in v.lower() or len(v) < 32:
                raise ValueError(
                    "Production SECRET_KEY must be set via environment and be at least 32 characters long."
                )
        return v


settings = Settings()
