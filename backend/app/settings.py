from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    admin_password: str = Field(alias="ADMIN_PASSWORD")
    admin_jwt_secret: str = Field(alias="ADMIN_JWT_SECRET")
    admin_jwt_ttl_minutes: int = Field(default=60, alias="ADMIN_JWT_TTL_MINUTES")
    admin_cookie_name: str = Field(default="admin_session", alias="ADMIN_COOKIE_NAME")
    admin_cookie_secure: bool = Field(default=True, alias="ADMIN_COOKIE_SECURE")
    admin_cookie_samesite: str = Field(default="none", alias="ADMIN_COOKIE_SAMESITE")
    backend_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        alias="BACKEND_ALLOWED_ORIGINS",
    )
    backend_cors_allow_credentials: bool = Field(default=True, alias="BACKEND_CORS_ALLOW_CREDENTIALS")
    redis_url: str = Field(alias="REDIS_URL")
    notion_token: str = Field(alias="NOTION_TOKEN")
    notion_api_version: str = Field(default="2026-03-11", alias="NOTION_API_VERSION")
    notion_database_id: str = Field(alias="NOTION_DATABASE_ID")
    notion_data_source_id: str = Field(alias="NOTION_DATA_SOURCE_ID")
    n8n_base_url: str = Field(alias="N8N_BASE_URL")
    n8n_shared_secret: str = Field(alias="N8N_SHARED_SECRET")
    n8n_webhook_register_path: str = Field(alias="N8N_WEBHOOK_REGISTER_PATH")
    n8n_webhook_complete_path: str = Field(alias="N8N_WEBHOOK_COMPLETE_PATH")
    admin_notification_email: str = Field(alias="ADMIN_NOTIFICATION_EMAIL")
    n8n_timeout_seconds: float = 30.0

    @field_validator("backend_allowed_origins", mode="before")
    @classmethod
    def split_allowed_origins(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @field_validator("admin_cookie_samesite")
    @classmethod
    def validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("ADMIN_COOKIE_SAMESITE must be one of lax/strict/none")
        return normalized
