from functools import lru_cache

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FastAPI Blog"
    debug: bool = False
    templates_dir: str = "templates"
    static_dir: str = "static"
    default_post_date: str = "April 23, 2025"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
