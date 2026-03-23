from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_API_VERSION = "2026-03-11"


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
