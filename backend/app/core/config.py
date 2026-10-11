from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "RideWave"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DATABASE_URL: str = "postgresql+psycopg://ridewave:ridewave_password@localhost:5432/ridewave_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # AI Configuration
    AI_ENABLED: bool = False
    LLM_PROVIDER: str = "openrouter"
    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "meta-llama/llama-3.2-3b-instruct:free"

    # Spatial defaults
    MAX_MATCHING_RADIUS_KM: float = 5.0
    H3_RESOLUTION: int = 8

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
