from functools import lru_cache

from pydantic import ConfigDict, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FastAPI Blog"
    debug: bool = False
    static_dir: str = "static"
    templates_dir: str = "templates"
    default_post_date: str = "April 23, 2025"
    secret_key:SecretStr
    algorithm:str = "HS256"
    access_token_expire_minutes: int=30
    s3_bucket_name: str | None = None
    s3_region: str = "us-east-1"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

max_upload_size_bytes: int = 5 * 1024 * 1024

# type: ignore[call-arg]
settings = get_settings()
