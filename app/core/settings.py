from pathlib import Path

from pydantic import EmailStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # PROJECT
    PROJECT_NAME: str = "FastAPI Backend"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    ENVIRONMENT: str = "local"

    # DATABASE
    POSTGRES_HOST: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_PORT: int = 5432

    # SYNCRONOUS DATABASE URL
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ASYNCRONOUS DATABASE URL
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # REDIS
    REDIS_URL: str = "redis://redis:6379/0"

    # NATS
    NATS_ENABLED: bool = False
    NATS_URL: str = "nats://nats:4222"
    NATS_EVENTS_STREAM: str = "EVENTS"
    NATS_EVENTS_SUBJECT_PREFIX: str = "events"
    NATS_DLQ_STREAM: str = "EVENTS_DLQ"
    NATS_CONSUMER_MAX_DELIVER: int = 3

    # SECURITY
    JWT_SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS]

    # FIRST SUPERUSER
    FIRST_SUPERUSER_EMAIL: EmailStr | None = None
    FIRST_SUPERUSER_PASSWORD: str | None = None
    FIRST_SUPERUSER_USERNAME: str = "admin"
    FIRST_SUPERUSER_PHONE_NUMBER: str = "+1234567890"

    # EMAIL (SMTP)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: EmailStr | None = None
    SMTP_FROM_NAME: str = "App"

    # FILE UPLOADS
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: list[str] = ["jpg", "jpeg", "png", "pdf", "doc", "docx"]

    # PAGINATION
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    @field_validator("ENVIRONMENT")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        allowed = {"local", "staging", "production", "test"}
        if value not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed!r}, got {value!r}")
        return value

    @model_validator(mode="after")
    def _validate_security(self) -> Settings:
        placeholder = "REPLACE_WITH_64_CHAR_RANDOM_STRING_IN_PRODUCTION"
        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
            raise ValueError("JWT_SECRET_KEY must be set and at least 32 characters long.")
        if placeholder == self.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY cannot be the example placeholder value.")
        return self

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.ENVIRONMENT != "production":
            return self

        if self.FIRST_SUPERUSER_PASSWORD and len(self.FIRST_SUPERUSER_PASSWORD) < 12:
            raise ValueError("FIRST_SUPERUSER_PASSWORD must be at least 12 characters in production.")

        required = {
            "POSTGRES_HOST": self.POSTGRES_HOST,
            "POSTGRES_USER": self.POSTGRES_USER,
            "POSTGRES_PASSWORD": self.POSTGRES_PASSWORD,
            "POSTGRES_DB": self.POSTGRES_DB,
            "REDIS_URL": self.REDIS_URL,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Production settings missing for: {', '.join(missing)}")

        return self


settings = Settings()
