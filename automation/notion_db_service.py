from __future__ import annotations

from dataclasses import dataclass, field

from automation.envfile import NotionAutomationConfig
from automation.notion_api import NotionClient, iter_database_data_sources, rich_text_to_plain_text
from automation.notion_schema import SchemaIssue, STATUS_NAME_MAPPING, validate_data_source_schema


class NotionDbAutomationError(RuntimeError):
    """Raised when ensure/validate cannot complete safely."""


@dataclass(slots=True)
class NotionDbResult:
    database_id: str
    data_source_id: str
    database_title: str
    created: bool
    warnings: list[str] = field(default_factory=list)


def _normalize_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("-", "").lower()


def _extract_database_id_from_data_source(data_source: dict[str, object]) -> str:
    parent = data_source.get("parent")
    if isinstance(parent, dict):
        database_id = parent.get("database_id")
        if isinstance(database_id, str) and database_id:
            return database_id
    raise NotionDbAutomationError("Could not determine database_id from data source response")


def _extract_database_title(database: dict[str, object]) -> str:
    title = rich_text_to_plain_text(database.get("title"))
    if title:
        return title
    return "<untitled>"


class NotionDatabaseService:
    def __init__(self, config: NotionAutomationConfig, client: NotionClient) -> None:
        self.config = config
        self.client = client

    def ensure(self) -> NotionDbResult:
        if self.config.notion_data_source_id:
            return self._ensure_from_data_source_id(self.config.notion_data_source_id)

        if self.config.notion_database_id:
            return self._ensure_from_database_id(self.config.notion_database_id)

        matches = self._find_exact_matches()
        if len(matches) > 1:
            ids = ", ".join(match["data_source_id"] for match in matches)
            raise NotionDbAutomationError(
                "Multiple exact-matching data sources were found; set NOTION_DATABASE_ID or "
                f"NOTION_DATA_SOURCE_ID explicitly. Matches: {ids}"
            )

        if len(matches) == 1:
            match = matches[0]
            return self._build_existing_result(match["database"], match["data_source"], created=False)

        return self._create_database()

    def validate(self) -> NotionDbResult:
        result = self._resolve_existing_target()
        data_source = self.client.retrieve_data_source(result.data_source_id)
        issues = validate_data_source_schema(self._extract_properties(data_source), require_status=True)
        if issues:
            raise NotionDbAutomationError(_format_schema_issues(issues))
        return result

    def _resolve_existing_target(self) -> NotionDbResult:
        if self.config.notion_data_source_id:
            return self._ensure_from_data_source_id(self.config.notion_data_source_id)
        if self.config.notion_database_id:
            return self._ensure_from_database_id(self.config.notion_database_id)

        matches = self._find_exact_matches()
        if not matches:
            raise NotionDbAutomationError(
                "No matching Notion database was found. Run ensure first or set NOTION_DATABASE_ID."
            )
        if len(matches) > 1:
            ids = ", ".join(match["data_source_id"] for match in matches)
            raise NotionDbAutomationError(
                "Multiple exact-matching data sources were found; set NOTION_DATABASE_ID or "
                f"NOTION_DATA_SOURCE_ID explicitly. Matches: {ids}"
            )
        match = matches[0]
        return self._build_existing_result(match["database"], match["data_source"], created=False)

    def _ensure_from_data_source_id(self, data_source_id: str) -> NotionDbResult:
        data_source = self.client.retrieve_data_source(data_source_id)
        database_id = _extract_database_id_from_data_source(data_source)
        database = self.client.retrieve_database(database_id)
        return self._build_existing_result(database, data_source, created=False)

    def _ensure_from_database_id(self, database_id: str) -> NotionDbResult:
        database = self.client.retrieve_database(database_id)
        data_source = self._select_single_data_source(database)
        return self._build_existing_result(database, data_source, created=False)

    def _create_database(self) -> NotionDbResult:
        if not self.config.notion_parent_page_id or not self.config.notion_database_title:
            raise NotionDbAutomationError("NOTION_PARENT_PAGE_ID and NOTION_DATABASE_TITLE are required")

        created_database = self.client.create_database(
            self.config.notion_parent_page_id,
            self.config.notion_database_title,
        )
        database_id = created_database.get("id")
        if not isinstance(database_id, str):
            raise NotionDbAutomationError("Notion create database response did not include a database id")

        database = self.client.retrieve_database(database_id)
        data_source = self._select_single_data_source(database)
        result = self._build_existing_result(database, data_source, created=True)
        result.warnings.append(
            "Status property is not created by the API. Create a manual status property named "
            "'Status' with options: Registered, In Progress, Completed."
        )
        return result

    def _build_existing_result(
        self,
        database: dict[str, object],
        data_source: dict[str, object],
        *,
        created: bool,
    ) -> NotionDbResult:
        issues = validate_data_source_schema(self._extract_properties(data_source), require_status=False)
        if issues:
            raise NotionDbAutomationError(_format_schema_issues(issues))

        database_id = database.get("id")
        data_source_id = data_source.get("id")
        if not isinstance(database_id, str) or not isinstance(data_source_id, str):
            raise NotionDbAutomationError("Notion target did not contain database/data source IDs")

        warnings = self._schema_warnings(data_source)
        return NotionDbResult(
            database_id=database_id,
            data_source_id=data_source_id,
            database_title=_extract_database_title(database),
            created=created,
            warnings=warnings,
        )

    def _find_exact_matches(self) -> list[dict[str, dict[str, object]]]:
        if not self.config.notion_database_title or not self.config.notion_parent_page_id:
            raise NotionDbAutomationError("NOTION_DATABASE_TITLE and NOTION_PARENT_PAGE_ID are required for search")

        desired_title = self.config.notion_database_title
        desired_parent = _normalize_id(self.config.notion_parent_page_id)
        matches: list[dict[str, dict[str, object]]] = []

        for data_source in self.client.search_data_sources_by_title(desired_title):
            title = rich_text_to_plain_text(data_source.get("title"))
            if title != desired_title:
                continue

            database_parent = data_source.get("database_parent")
            if not isinstance(database_parent, dict):
                continue
            if _normalize_id(database_parent.get("page_id")) != desired_parent:
                continue

            database_id = _extract_database_id_from_data_source(data_source)
            database = self.client.retrieve_database(database_id)
            matches.append(
                {
                    "database": database,
                    "data_source": self.client.retrieve_data_source(data_source["id"]),
                    "data_source_id": data_source["id"],
                }
            )

        return matches

    def _select_single_data_source(self, database: dict[str, object]) -> dict[str, object]:
        data_sources = list(iter_database_data_sources(database))
        if len(data_sources) != 1:
            raise NotionDbAutomationError(
                f"Expected exactly 1 data source under database {database.get('id')}, found {len(data_sources)}"
            )

        data_source_id = data_sources[0].get("id")
        if not isinstance(data_source_id, str):
            raise NotionDbAutomationError("Database response did not include a valid data source id")
        return self.client.retrieve_data_source(data_source_id)

    def _extract_properties(self, data_source: dict[str, object]) -> dict[str, dict[str, object]]:
        properties = data_source.get("properties")
        if not isinstance(properties, dict):
            raise NotionDbAutomationError("Data source response did not include a properties object")

        parsed: dict[str, dict[str, object]] = {}
        for key, value in properties.items():
            if isinstance(key, str) and isinstance(value, dict):
                parsed[key] = value
        return parsed

    def _schema_warnings(self, data_source: dict[str, object]) -> list[str]:
        issues = validate_data_source_schema(self._extract_properties(data_source), require_status=True)
        if not issues:
            return []

        return [
            "Manual follow-up required: "
            + _format_schema_issues(issues)
            + " Keep the Notion schema aligned with the automation contract. Use English status labels and map Korean product states as "
            + ", ".join(f"{source}->{target}" for source, target in STATUS_NAME_MAPPING.items())
            + "."
        ]


def _format_schema_issues(issues: list[SchemaIssue]) -> str:
    return "; ".join(issue.render() for issue in issues)
