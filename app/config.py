from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
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
    
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    llm_timeout_s: float = 120.0
    llm_helper_timeout_s: float = 30.0
    
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    
    @field_validator("database_url")
    @classmethod
    def postgres_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql"):
            raise ValueError("POLICY_DATABASE_URL must be a postgresql URL.")
        return value
    
    @field_validator("db_pool_size")
    @classmethod
    def pool_size_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("POLICY_DB_POOL_SIZE must be at least 1.")
        return value
    
    @field_validator("llm_timeout_s", "llm_helper_timeout_s")
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
