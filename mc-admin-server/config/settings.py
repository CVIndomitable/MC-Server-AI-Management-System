from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    secret_key: str
    access_token_expire_minutes: int = 10080

    anthropic_api_key: str
    anthropic_base_url: str = "https://api.anthropic.com"
    model_flash: str = "MiMo-V2-Flash"
    model_standard: str = "MiMo-V2-Omni"
    model_pro: str = "mimo-v2-pro"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    mod_auth_token: str

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173", "http://192.168.1.6:8081", "*"]

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
