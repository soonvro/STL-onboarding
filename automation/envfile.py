from __future__ import annotations

import os
from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path


DEFAULT_API_VERSION = "2026-03-11"
DEFAULT_N8N_IMAGE = "n8nio/n8n:2.13.3"
DEFAULT_N8N_MEMORY = "2Gi"
DEFAULT_N8N_REGION = "asia-northeast3"
DEFAULT_N8N_SCALING = "1"
DEFAULT_N8N_SERVICE_NAME = "n8n-demo"
DEFAULT_BACKEND_MEMORY = "1Gi"
DEFAULT_BACKEND_SERVICE_NAME = "qna-backend"
DEFAULT_REDIS_INSTANCE_NAME = "qna-redis"
DEFAULT_REDIS_REGION = "asia-northeast3"
DEFAULT_REDIS_SIZE_GB = "1"
DEFAULT_REDIS_NETWORK = "default"
DEFAULT_REDIS_REDIS_VERSION = "redis_7_0"
DEFAULT_TIMEZONE = "Asia/Seoul"


class ConfigError(ValueError):
    """Raised when required environment variables are missing."""


def load_dotenv_defaults(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _required_env(name: str) -> str:
    value = _optional_env(name)
    if not value:
        raise ConfigError(f"{name} is required")
    return value


def _required_email(name: str) -> str:
    value = _required_env(name)
    email = _extract_email_address(value)
    if not email:
        raise ConfigError(f"{name} must contain a valid email address")
    return email


def _extract_email_address(value: str | None) -> str | None:
    _, email = parseaddr((value or "").strip())
    return email or None


def _parse_bool(value: str | None, *, name: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be one of true/false/1/0/yes/no/on/off")


@dataclass(slots=True)
class NotionAutomationConfig:
    notion_token: str
    notion_api_version: str
    notion_parent_page_id: str | None
    notion_database_title: str | None
    notion_database_id: str | None
    notion_data_source_id: str | None

    @classmethod
    def from_environment(cls) -> "NotionAutomationConfig":
        token = _optional_env("NOTION_TOKEN")
        if not token:
            raise ConfigError("NOTION_TOKEN is required")

        return cls(
            notion_token=token,
            notion_api_version=_optional_env("NOTION_API_VERSION") or DEFAULT_API_VERSION,
            notion_parent_page_id=_optional_env("NOTION_PARENT_PAGE_ID"),
            notion_database_title=_optional_env("NOTION_DATABASE_TITLE"),
            notion_database_id=_optional_env("NOTION_DATABASE_ID"),
            notion_data_source_id=_optional_env("NOTION_DATA_SOURCE_ID"),
        )

    def validate_for_action(self, action: str) -> None:
        if action == "ensure":
            missing = []
            if not self.notion_parent_page_id:
                missing.append("NOTION_PARENT_PAGE_ID")
            if not self.notion_database_title:
                missing.append("NOTION_DATABASE_TITLE")
            if missing:
                raise ConfigError(", ".join(missing) + " is required for ensure")
            return

        if action == "validate":
            has_lookup = self.notion_database_id or self.notion_data_source_id
            has_search = self.notion_parent_page_id and self.notion_database_title
            if has_lookup or has_search:
                return
            raise ConfigError(
                "validate requires NOTION_DATABASE_ID or NOTION_DATA_SOURCE_ID, "
                "or both NOTION_PARENT_PAGE_ID and NOTION_DATABASE_TITLE"
            )

        raise ConfigError(f"Unsupported action: {action}")


@dataclass(slots=True)
class N8nCloudRunConfig:
    gcp_project_id: str
    gcp_region: str
    n8n_service_name: str
    n8n_image: str
    n8n_memory: str
    n8n_scaling: str
    n8n_timezone: str
    n8n_shared_secret: str
    n8n_base_url: str | None

    @classmethod
    def from_environment(cls) -> "N8nCloudRunConfig":
        return cls(
            gcp_project_id=_required_env("GCP_PROJECT_ID"),
            gcp_region=_optional_env("GCP_REGION") or DEFAULT_N8N_REGION,
            n8n_service_name=_optional_env("N8N_SERVICE_NAME") or DEFAULT_N8N_SERVICE_NAME,
            n8n_image=_optional_env("N8N_IMAGE") or DEFAULT_N8N_IMAGE,
            n8n_memory=_optional_env("N8N_MEMORY") or DEFAULT_N8N_MEMORY,
            n8n_scaling=_optional_env("N8N_SCALING") or DEFAULT_N8N_SCALING,
            n8n_timezone=_optional_env("N8N_TIMEZONE") or DEFAULT_TIMEZONE,
            n8n_shared_secret=_required_env("N8N_SHARED_SECRET"),
            n8n_base_url=_optional_env("N8N_BASE_URL"),
        )

    def validate_for_action(self, action: str) -> None:
        if action == "deploy":
            return
        if action == "describe":
            return
        raise ConfigError(f"Unsupported action: {action}")


@dataclass(slots=True)
class N8nBootstrapConfig:
    n8n_base_url: str
    n8n_api_key: str
    n8n_shared_secret: str
    n8n_webhook_register_path: str
    n8n_webhook_complete_path: str
    n8n_from_email: str
    n8n_notion_credential_name: str
    n8n_smtp_credential_name: str
    n8n_notion_credential_id: str | None
    n8n_smtp_credential_id: str | None
    notion_token: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_secure: bool

    @classmethod
    def from_environment(cls) -> "N8nBootstrapConfig":
        smtp_port_value = _required_env("SMTP_PORT")
        try:
            smtp_port = int(smtp_port_value)
        except ValueError as exc:
            raise ConfigError("SMTP_PORT must be an integer") from exc

        return cls(
            n8n_base_url=_required_env("N8N_BASE_URL"),
            n8n_api_key=_required_env("N8N_API_KEY"),
            n8n_shared_secret=_required_env("N8N_SHARED_SECRET"),
            n8n_webhook_register_path=_required_env("N8N_WEBHOOK_REGISTER_PATH"),
            n8n_webhook_complete_path=_required_env("N8N_WEBHOOK_COMPLETE_PATH"),
            n8n_from_email=_required_env("N8N_FROM_EMAIL"),
            n8n_notion_credential_name=_optional_env("N8N_NOTION_CREDENTIAL_NAME") or "QnA Notion",
            n8n_smtp_credential_name=_optional_env("N8N_SMTP_CREDENTIAL_NAME") or "QnA SMTP",
            n8n_notion_credential_id=_optional_env("N8N_NOTION_CREDENTIAL_ID"),
            n8n_smtp_credential_id=_optional_env("N8N_SMTP_CREDENTIAL_ID"),
            notion_token=_required_env("NOTION_TOKEN"),
            smtp_host=_required_env("SMTP_HOST"),
            smtp_port=smtp_port,
            smtp_user=_required_env("SMTP_USER"),
            smtp_password=_required_env("SMTP_PASSWORD"),
            smtp_secure=_parse_bool(_required_env("SMTP_SECURE"), name="SMTP_SECURE"),
        )

    def validate_for_action(self, action: str) -> None:
        if action in {"sync", "verify"}:
            return
        raise ConfigError(f"Unsupported action: {action}")


@dataclass(slots=True)
class N8nIntegrationTestConfig:
    n8n_base_url: str
    n8n_shared_secret: str
    n8n_webhook_register_path: str
    n8n_webhook_complete_path: str
    notion_token: str
    notion_api_version: str
    notion_database_id: str
    admin_email: str
    requester_email: str

    @classmethod
    def from_environment(cls) -> "N8nIntegrationTestConfig":
        fallback_email = (
            _extract_email_address(_optional_env("N8N_FROM_EMAIL"))
            or _extract_email_address(_optional_env("SMTP_USER"))
        )
        admin_email = _extract_email_address(_optional_env("N8N_TEST_ADMIN_EMAIL")) or fallback_email
        requester_email = _extract_email_address(_optional_env("N8N_TEST_REQUESTER_EMAIL")) or admin_email

        if not admin_email:
            raise ConfigError(
                "N8N_TEST_ADMIN_EMAIL is required when N8N_FROM_EMAIL/SMTP_USER does not contain a valid email address"
            )
        if not requester_email:
            raise ConfigError("Unable to derive N8N_TEST_REQUESTER_EMAIL")

        return cls(
            n8n_base_url=_required_env("N8N_BASE_URL"),
            n8n_shared_secret=_required_env("N8N_SHARED_SECRET"),
            n8n_webhook_register_path=_required_env("N8N_WEBHOOK_REGISTER_PATH"),
            n8n_webhook_complete_path=_required_env("N8N_WEBHOOK_COMPLETE_PATH"),
            notion_token=_required_env("NOTION_TOKEN"),
            notion_api_version=_optional_env("NOTION_API_VERSION") or DEFAULT_API_VERSION,
            notion_database_id=_required_env("NOTION_DATABASE_ID"),
            admin_email=admin_email,
            requester_email=requester_email,
        )

    def validate_for_action(self, action: str) -> None:
        if action == "run":
            return
        raise ConfigError(f"Unsupported action: {action}")


@dataclass(slots=True)
class BackendCloudRunConfig:
    gcp_project_id: str
    gcp_region: str
    backend_service_name: str
    backend_image: str
    backend_memory: str
    backend_vpc_network: str
    backend_vpc_subnet: str
    backend_vpc_egress: str

    @classmethod
    def from_environment(cls) -> "BackendCloudRunConfig":
        project_id = _required_env("GCP_PROJECT_ID")
        service_name = _optional_env("BACKEND_SERVICE_NAME") or DEFAULT_BACKEND_SERVICE_NAME
        image = _optional_env("BACKEND_IMAGE") or f"gcr.io/{project_id}/{service_name}"
        return cls(
            gcp_project_id=project_id,
            gcp_region=_optional_env("GCP_REGION") or DEFAULT_N8N_REGION,
            backend_service_name=service_name,
            backend_image=image,
            backend_memory=_optional_env("BACKEND_MEMORY") or DEFAULT_BACKEND_MEMORY,
            backend_vpc_network=_optional_env("BACKEND_VPC_NETWORK") or DEFAULT_REDIS_NETWORK,
            backend_vpc_subnet=_optional_env("BACKEND_VPC_SUBNET") or DEFAULT_REDIS_NETWORK,
            backend_vpc_egress=_optional_env("BACKEND_VPC_EGRESS") or "private-ranges-only",
        )

    def validate_for_action(self, action: str) -> None:
        if action in {"deploy", "describe"}:
            return
        raise ConfigError(f"Unsupported action: {action}")


@dataclass(slots=True)
class RedisAutomationConfig:
    gcp_project_id: str
    redis_instance_name: str
    redis_region: str
    redis_size_gb: int
    redis_network: str
    redis_version: str

    @classmethod
    def from_environment(cls) -> "RedisAutomationConfig":
        size_value = _optional_env("REDIS_SIZE_GB") or DEFAULT_REDIS_SIZE_GB
        try:
            size_gb = int(size_value)
        except ValueError as exc:
            raise ConfigError("REDIS_SIZE_GB must be an integer") from exc

        return cls(
            gcp_project_id=_required_env("GCP_PROJECT_ID"),
            redis_instance_name=_optional_env("REDIS_INSTANCE_NAME") or DEFAULT_REDIS_INSTANCE_NAME,
            redis_region=_optional_env("REDIS_REGION") or DEFAULT_REDIS_REGION,
            redis_size_gb=size_gb,
            redis_network=_optional_env("REDIS_NETWORK") or DEFAULT_REDIS_NETWORK,
            redis_version=_optional_env("REDIS_REDIS_VERSION") or DEFAULT_REDIS_REDIS_VERSION,
        )

    def validate_for_action(self, action: str) -> None:
        if action in {"create", "describe", "destroy"}:
            return
        raise ConfigError(f"Unsupported action: {action}")


@dataclass(slots=True)
class BackendIntegrationTestConfig:
    backend_base_url: str
    admin_password: str
    notion_token: str
    notion_api_version: str
    requester_email: str

    @classmethod
    def from_environment(cls) -> "BackendIntegrationTestConfig":
        requester_email = (
            _extract_email_address(_optional_env("BACKEND_TEST_REQUESTER_EMAIL"))
            or _extract_email_address(_optional_env("N8N_TEST_REQUESTER_EMAIL"))
            or _extract_email_address(_optional_env("SMTP_USER"))
            or _extract_email_address(_optional_env("N8N_FROM_EMAIL"))
        )
        if not requester_email:
            raise ConfigError(
                "BACKEND_TEST_REQUESTER_EMAIL is required when SMTP_USER/N8N_FROM_EMAIL does not contain a valid email address"
            )

        return cls(
            backend_base_url=_required_env("BACKEND_BASE_URL"),
            admin_password=_required_env("ADMIN_PASSWORD"),
            notion_token=_required_env("NOTION_TOKEN"),
            notion_api_version=_optional_env("NOTION_API_VERSION") or DEFAULT_API_VERSION,
            requester_email=requester_email,
        )

    def validate_for_action(self, action: str) -> None:
        if action == "run":
            return
        raise ConfigError(f"Unsupported action: {action}")
