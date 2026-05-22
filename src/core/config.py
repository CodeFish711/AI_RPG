from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mimo_api_key: str = Field(default="", validation_alias="MIMO_API_KEY")
    mimo_base_url: str = Field(default="https://token-plan-cn.xiaomimimo.com/v1", validation_alias="MIMO_BASE_URL")
    mimo_model: str = Field(default="mimo-v2.5-pro", validation_alias="MIMO_MODEL")

