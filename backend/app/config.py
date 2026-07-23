from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://dtai:dtai@localhost:5432/dtai"
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM — Phase 25：所有 provider 設定改由 DB 提供（admin 後台管理）。
    # 此處只保留呼叫端共用的限制與 timeout，不再有任何 endpoint / key 的預設值。

    # LLM Limits
    LLM_MAX_TOKENS_PER_CALL: int = 2048
    LLM_PROJECT_RPM_LIMIT: int = 30
    # Phase 37: lowered 300 → 116 to match measured sustainable throughput
    # (llm-bench-report §6: two-provider knee ≈ 145 rpm × 0.8). Env-overridable.
    LLM_GLOBAL_RPM_LIMIT: int = 116
    LLM_CALL_TIMEOUT_SECONDS: int = 60
    LLM_STREAM_CONNECT_TIMEOUT_SECONDS: int = 15
    LLM_PROVIDER_COOLDOWN_SECONDS: int = 30
    LLM_PROVIDER_REGISTRY_TTL_SECONDS: int = 30
    # Phase 42 D5 (G14 / #35, spec 20 §13.2)：LLM 持續不可用 → fail-stop。
    # reactive 連續硬失敗門檻 / proactive 健康檢查間隔（同門檻套用 proactive streak）。
    LLM_DOWN_CONSECUTIVE_FAILURES: int = 3
    LLM_HEALTH_CHECK_INTERVAL_SECONDS: int = 30

    # Embedding (Qwen3-Embedding-8B)
    EMBEDDING_BASE_URL: str = "https://embedding.example.com/v1"
    EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-8B"
    EMBEDDING_API_KEY: str = "dummy"

    # Yjs Sidecar
    SIDECAR_URL: str = "http://localhost:4000"

    # App
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:5173"

    # Secret encryption (Phase 26 / S2)
    # Fernet key (url-safe base64, 32 bytes). Required in non-dev.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    LLM_PROVIDER_KEY_MASTER: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
