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

    cache_ttl_seconds: int = 3600  # 命令缓存过期时间（秒），默认1小时
    cache_max_size: int = 500       # 最大缓存条目数

    # 命令审核配置
    review_ai_enabled: bool = True          # 是否启用AI审核层
    review_confirm_timeout: int = 120       # 人工确认超时时间（秒）
    review_burst_window: int = 30           # 频率检测时间窗口（秒）
    review_burst_threshold: int = 3         # 频率检测阈值
    review_give_amount_threshold: int = 1000  # give命令数量异常阈值

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
