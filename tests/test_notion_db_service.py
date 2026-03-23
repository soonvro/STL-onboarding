from __future__ import annotations

import unittest

from automation.envfile import NotionAutomationConfig
from automation.notion_db_service import NotionDatabaseService, NotionDbAutomationError


def rich_text_value(value: str) -> list[dict[str, object]]:
    return [{"type": "text", "plain_text": value, "text": {"content": value}}]


def make_data_source(
    *,
    data_source_id: str = "ds-1",
    database_id: str = "db-1",
    parent_page_id: str = "page-1",
    title: str = "Q&A Inquiries",
    include_status: bool = False,
    include_request_id: bool = False,
    status_type: str = "status",
    status_options: list[str] | None = None,
) -> dict[str, object]:
    properties: dict[str, dict[str, object]] = {
        "Title": {"type": "title", "title": {}},
        "Name": {"type": "rich_text", "rich_text": {}},
        "Email": {"type": "email", "email": {}},
        "Phone": {"type": "phone_number", "phone_number": {}},
        "Body": {"type": "rich_text", "rich_text": {}},
        "DedupKey": {"type": "rich_text", "rich_text": {}},
        "Resolution": {"type": "rich_text", "rich_text": {}},
        "CreatedAt": {"type": "created_time", "created_time": {}},
        "UpdatedAt": {"type": "last_edited_time", "last_edited_time": {}},
    }
    if include_request_id:
        properties["RequestId"] = {"type": "rich_text", "rich_text": {}}
    if include_status:
        properties["Status"] = {
            "type": status_type,
            status_type: {
                "options": [{"name": option} for option in (status_options or ["Registered", "In Progress", "Completed"])]
            },
        }

    return {
        "object": "data_source",
        "id": data_source_id,
        "title": rich_text_value(title),
        "parent": {
            "type": "database_id",
            "database_id": database_id,
        },
        "database_parent": {
            "type": "page_id",
            "page_id": parent_page_id,
        },
        "properties": properties,
    }


def make_database(
    *,
    database_id: str = "db-1",
    data_source_id: str = "ds-1",
    title: str = "Q&A Inquiries",
) -> dict[str, object]:
    return {
        "object": "database",
        "id": database_id,
        "title": rich_text_value(title),
        "data_sources": [{"id": data_source_id, "name": title}],
    }


class FakeNotionClient:
    def __init__(
        self,
        *,
        search_results: list[dict[str, object]] | None = None,
        databases: dict[str, dict[str, object]] | None = None,
        data_sources: dict[str, dict[str, object]] | None = None,
        created_database: dict[str, object] | None = None,
    ) -> None:
        self.search_results = search_results or []
        self.databases = databases or {}
        self.data_sources = data_sources or {}
        self.created_database = created_database
        self.created_with: tuple[str, str] | None = None

    def search_data_sources_by_title(self, _: str) -> list[dict[str, object]]:
        return self.search_results

    def retrieve_database(self, database_id: str) -> dict[str, object]:
        return self.databases[database_id]

    def retrieve_data_source(self, data_source_id: str) -> dict[str, object]:
        return self.data_sources[data_source_id]

    def create_database(self, parent_page_id: str, database_title: str) -> dict[str, object]:
        self.created_with = (parent_page_id, database_title)
        if self.created_database is None:
            raise AssertionError("create_database was not expected")
        return self.created_database


class NotionDatabaseServiceTest(unittest.TestCase):
    def make_config(self, **overrides: str | None) -> NotionAutomationConfig:
        base = {
            "notion_token": "token",
            "notion_api_version": "2026-03-11",
            "notion_parent_page_id": "page-1",
            "notion_database_title": "Q&A Inquiries",
            "notion_database_id": None,
            "notion_data_source_id": None,
        }
        base.update(overrides)
        return NotionAutomationConfig(**base)

    def test_ensure_reuses_existing_database_when_exact_match_exists(self) -> None:
        data_source = make_data_source()
        database = make_database()
        client = FakeNotionClient(
            search_results=[data_source],
            databases={"db-1": database},
            data_sources={"ds-1": data_source},
        )

        result = NotionDatabaseService(self.make_config(), client).ensure()

        self.assertFalse(result.created)
        self.assertEqual(result.database_id, "db-1")
        self.assertEqual(result.data_source_id, "ds-1")
        self.assertTrue(result.warnings)
        self.assertIn("Status", result.warnings[0])

    def test_ensure_creates_database_when_no_match_exists(self) -> None:
        created_database = make_database(database_id="db-new", data_source_id="ds-new")
        created_data_source = make_data_source(data_source_id="ds-new", database_id="db-new")
        client = FakeNotionClient(
            search_results=[],
            databases={"db-new": created_database},
            data_sources={"ds-new": created_data_source},
            created_database={"id": "db-new"},
        )

        result = NotionDatabaseService(self.make_config(), client).ensure()

        self.assertTrue(result.created)
        self.assertEqual(result.database_id, "db-new")
        self.assertEqual(result.data_source_id, "ds-new")
        self.assertEqual(client.created_with, ("page-1", "Q&A Inquiries"))
        self.assertTrue(any("Status property is not created by the API" in warning for warning in result.warnings))

    def test_ensure_fails_on_ambiguous_exact_matches(self) -> None:
        first = make_data_source(data_source_id="ds-1")
        second = make_data_source(data_source_id="ds-2")
        client = FakeNotionClient(
            search_results=[first, second],
            databases={"db-1": make_database(data_source_id="ds-1"), "db-2": make_database(database_id="db-2", data_source_id="ds-2")},
            data_sources={"ds-1": first, "ds-2": second},
        )

        with self.assertRaises(NotionDbAutomationError) as context:
            NotionDatabaseService(self.make_config(), client).ensure()

        self.assertIn("Multiple exact-matching data sources", str(context.exception))

    def test_validate_fails_when_status_property_is_missing(self) -> None:
        data_source = make_data_source(include_status=False)
        database = make_database()
        client = FakeNotionClient(databases={"db-1": database}, data_sources={"ds-1": data_source})
        config = self.make_config(notion_database_id="db-1")

        with self.assertRaises(NotionDbAutomationError) as context:
            NotionDatabaseService(config, client).validate()

        self.assertIn("Status", str(context.exception))

    def test_validate_succeeds_when_full_schema_exists(self) -> None:
        data_source = make_data_source(include_status=True)
        database = make_database()
        client = FakeNotionClient(databases={"db-1": database}, data_sources={"ds-1": data_source})
        config = self.make_config(notion_database_id="db-1")

        result = NotionDatabaseService(config, client).validate()

        self.assertEqual(result.database_id, "db-1")
        self.assertEqual(result.data_source_id, "ds-1")
        self.assertFalse(result.warnings)

    def test_validate_fails_when_status_options_are_wrong(self) -> None:
        data_source = make_data_source(include_status=True, status_options=["Draft", "Done"])
        database = make_database()
        client = FakeNotionClient(databases={"db-1": database}, data_sources={"ds-1": data_source})
        config = self.make_config(notion_database_id="db-1")

        with self.assertRaises(NotionDbAutomationError) as context:
            NotionDatabaseService(config, client).validate()

        self.assertIn("Registered", str(context.exception))

    def test_validate_fails_when_request_id_property_is_present(self) -> None:
        data_source = make_data_source(include_status=True, include_request_id=True)
        database = make_database()
        client = FakeNotionClient(databases={"db-1": database}, data_sources={"ds-1": data_source})
        config = self.make_config(notion_database_id="db-1")

        with self.assertRaises(NotionDbAutomationError) as context:
            NotionDatabaseService(config, client).validate()

        self.assertIn("RequestId", str(context.exception))
