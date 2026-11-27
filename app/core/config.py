from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class InfraSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POLICY_",
        env_file=".env",
        extra="ignore",
        # Validation errors must not echo the rejected value: a mistyped
        # database URL still contains the password.
        hide_input_in_errors=True,
    )
    
    database_url: SecretStr
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_connect_timeout_s: int = 5
    
    # 127.0.0.1, not "localhost": on Windows, localhost tries IPv6 (::1)
    # first and Ollama listens on IPv4 only, costing ~2 s per new connection.
    ollama_host: str = "http://127.0.0.1:11434"
    # "ollama": local Ollama (default). "openai": any OpenAI-compatible
    # /chat/completions API (Groq, Gemini, OpenRouter, or Ollama's own /v1),
    # configured by the three settings below. See app/rag/llm.py.
    llm_provider: Literal["ollama", "openai"] = "ollama"
    llm_base_url: str = ""
    llm_api_key: SecretStr | None = None
    # Sent as "reasoning_effort" when set (e.g. "low" for gpt-oss models):
    # reasoning tokens count against hosted rate limits.
    llm_reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    llm_model: str = "qwen3:8b"
    judge_model: str = "qwen3:8b"
    # The judge thinks before scoring and can exceed the answer budget on
    # long answers; eval-only, so a longer wait is acceptable.
    judge_timeout_s: float = 300.0
    llm_timeout_s: float = 120.0
    llm_helper_timeout_s: float = 30.0
    llm_keep_alive: str = "30m"

    # Concurrent LLM calls per API process. Match OLLAMA_NUM_PARALLEL: a
    # higher value only moves the queue into Ollama, where it is unbounded.
    # Measured: the local Ollama serves one generation at a time.
    llm_max_concurrency: int = 1
    llm_queue_timeout_s: float = 10.0

    # Per-user request budgets (fixed one-minute windows).
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["redis", "memory"] = "redis"
    rate_limit_redis_url: str = "redis://127.0.0.1:6379/2"
    rate_limit_llm_per_minute: int = 10
    rate_limit_search_per_minute: int = 60
    # Sign-in attempts (successful or not), per username and per client IP:
    # slows password guessing against one account and spraying across many.
    rate_limit_login_per_minute: int = 10
    rate_limit_login_ip_per_minute: int = 60
    
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Same model, two runtimes (ingest/embeddings.py): "sentence-transformers"
    # (PyTorch; local, ingestion, eval) or "onnx" (onnxruntime; the slim
    # deployment image). The ONNX directory holds model.onnx + tokenizer.json.
    embedding_backend: Literal["sentence-transformers", "onnx"] = "sentence-transformers"
    embedding_onnx_dir: str = ""

    # Browser origins allowed to call the API cross-origin, comma-separated
    # (e.g. "https://policy-copilot.vercel.app"). Empty: no CORS headers,
    # which is right when the frontend is served from the API's origin.
    cors_origins: str = ""
    
    # 127.0.0.1, not "localhost", for every host-side address: compose binds
    # Postgres and Redis to IPv4 loopback only, and on Windows "localhost"
    # tries IPv6 (::1) first and stalls before falling back.
    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/1"
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    
    warmup_on_startup: bool = True
    readiness_cache_s: float = 5.0

    
    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def provider_settings_complete(self):
        if self.llm_provider == "openai" and not self.llm_base_url:
            raise ValueError("POLICY_LLM_BASE_URL is required when POLICY_LLM_PROVIDER=openai.")
        if self.embedding_backend == "onnx" and not self.embedding_onnx_dir:
            raise ValueError("POLICY_EMBEDDING_ONNX_DIR is required when POLICY_EMBEDDING_BACKEND=onnx.")
        return self

    @field_validator("database_url")
    @classmethod
    def postgres_url(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        # Hosted Postgres (Neon, Supabase) hands out "postgresql://" or
        # "postgres://" URLs, which SQLAlchemy maps to psycopg2; this project
        # uses psycopg 3.
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url[len(prefix):]
        if not url.startswith("postgresql"):
            raise ValueError("POLICY_DATABASE_URL must be a postgresql URL.")
        return SecretStr(url)
    
    @field_validator(
        "db_pool_size",
        "llm_max_concurrency",
        "rate_limit_llm_per_minute",
        "rate_limit_search_per_minute",
        "rate_limit_login_per_minute",
        "rate_limit_login_ip_per_minute",
    )
    @classmethod
    def at_least_one(cls, value: int, info) -> int:
        if value < 1:
            raise ValueError(f"POLICY_{info.field_name.upper()} must be at least 1.")
        return value

    @field_validator(
        "llm_timeout_s", "llm_helper_timeout_s", "llm_queue_timeout_s", "judge_timeout_s"
    )
    @classmethod
    def timeout_positive(cls, value: float, info) -> float:
        if value <= 0:
            raise ValueError(
                f"POLICY_{info.field_name.upper()} must be greater than 0."
            )
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POLICY_",
        env_file=".env",
        extra="ignore",
        # A too-short JWT secret must not be printed in the error.
        hide_input_in_errors=True,
    )
    
     
    jwt_secret: SecretStr
    # One-click sign-in as sample users (POST /auth/demo). For showcase
    # deployments only: anyone who can reach the API can use it.
    demo_mode: bool = False
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "policy-copilot"
    jwt_audience: str = "policy-copilot-api"
    jwt_ttl_minutes: int = 60
    
    @field_validator("jwt_secret")
    @classmethod
    def secret_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError(
                "POLICY_JWT_SECRET must be least 32 characters"
            )
        
        return value
    
    @field_validator("jwt_ttl_minutes")
    @classmethod
    def ttl_in_range(cls, value: int) -> int:
        if not 1 <= value <= 24*60:
            raise ValueError("POLICY_JWT_TTL_MINUTES must be 1...1440")
        
        return value
    

@lru_cache
def get_settings() -> Settings:
    return Settings()

@lru_cache
def get_infra_settings() -> InfraSettings:
    return InfraSettings()


if __name__ == "__main__":
    # Print effective settings; SecretStr values are masked.
    print(get_infra_settings().model_dump_json(indent=2))
