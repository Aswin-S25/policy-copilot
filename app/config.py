from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POLICY_",
        env_file=".env",
        extra="ignore"
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