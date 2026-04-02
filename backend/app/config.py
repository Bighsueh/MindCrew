from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://dtai:dtai@localhost:5432/dtai"
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM
    LLM_PROVIDER: str = "vllm"
    VLLM_BASE_URL: str = "https://vllm.example.com/v1"
    VLLM_MODEL_NAME: str = "openai/gpt-oss-20b"
    VLLM_API_KEY: str = "dummy"

    # LLM Fallback
    LLM_FALLBACK_PROVIDER: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_DEPLOYMENT: str | None = None
    AZURE_OPENAI_API_VERSION: str | None = None

    # LLM Limits
    LLM_MAX_TOKENS_PER_CALL: int = 2048
    LLM_PROJECT_RPM_LIMIT: int = 30
    LLM_GLOBAL_RPM_LIMIT: int = 300
    LLM_CALL_TIMEOUT_SECONDS: int = 25

    # Embedding (Qwen3-Embedding-8B)
    EMBEDDING_BASE_URL: str = "https://embedding.example.com/v1"
    EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-8B"
    EMBEDDING_API_KEY: str = "dummy"

    # Yjs Sidecar
    SIDECAR_URL: str = "http://localhost:4000"

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
