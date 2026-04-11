from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    secret_key: str
    access_token_expire_minutes: int = 10080

    anthropic_api_key: str
    model_name: str = "claude-sonnet-4-6"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    mod_auth_token: str

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
