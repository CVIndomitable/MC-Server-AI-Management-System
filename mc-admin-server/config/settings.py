from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    secret_key: str
    access_token_expire_minutes: int = 10080

    anthropic_api_key: str
    model_name: str = "claude-haiku-4-5"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    mod_auth_token: str

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    @field_validator("secret_key", "anthropic_api_key", "mod_auth_token")
    @classmethod
    def validate_required_fields(cls, v: str, info) -> str:
        if not v or v.strip() == "":
            raise ValueError(f"{info.field_name} must not be empty")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
