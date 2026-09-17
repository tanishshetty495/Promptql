"""
Application configuration management.
"""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import List, Union
import secrets


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "PromptQL"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")

    # Security
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    ENCRYPTION_KEY: str = Field(...)  # 32-byte key for credential encryption

    # Database (app metadata)
    DATABASE_URL: str = Field(...)  # AsyncPG URL for app metadata DB

    # LLM Settings
    GROQ_API_KEY: str = Field(...)
    LLM_MODEL: str = Field(default="mixtral-8x7b-32768")
    LLM_MAX_RETRIES: int = Field(default=3)
    LLM_TIMEOUT: int = Field(default=30)  # seconds

    # Embedding Settings
    EMBEDDING_MODEL: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    EMBEDDING_BATCH_SIZE: int = Field(default=32)

    # Query Safety Settings
    STATEMENT_TIMEOUT_MS: int = Field(default=10000)  # 10 seconds
    MAX_OUTPUT_ROWS: int = Field(default=100)
    SESSION_READ_ONLY: bool = Field(default=True)

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=60)

    # CORS
    BACKEND_CORS_ORIGINS: List[Union[str, str]] = Field(
        default=["http://localhost:3000", "http://localhost:8080"]
    )

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }


settings = Settings()