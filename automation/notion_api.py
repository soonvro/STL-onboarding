from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from automation.notion_schema import CREATABLE_DATABASE_PROPERTIES


class NotionApiError(RuntimeError):
    """Raised when the Notion API returns an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class NotionClient:
    token: str
    api_version: str
    base_url: str = "https://api.notion.com/v1"
    timeout_seconds: float = 30.0
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.api_version,
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NotionClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, method: str, path: str, *, json: dict[str, object] | None = None) -> dict[str, object]:
        response = self._client.request(method, path, json=json)
        if response.is_success:
            return response.json()

        message = f"Notion API request failed with {response.status_code}"
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if isinstance(payload, dict):
            code = payload.get("code")
            api_message = payload.get("message")
            if isinstance(code, str) and isinstance(api_message, str):
                message = f"{message}: {code} - {api_message}"
            elif isinstance(api_message, str):
                message = f"{message}: {api_message}"

        raise NotionApiError(message, status_code=response.status_code)

    def create_database(self, parent_page_id: str, database_title: str) -> dict[str, object]:
        payload = {
            "parent": {
                "type": "page_id",
                "page_id": parent_page_id,
            },
            "title": [
                {
                    "type": "text",
                    "text": {"content": database_title},
                }
            ],
            "is_inline": False,
            "initial_data_source": {
                "properties": CREATABLE_DATABASE_PROPERTIES,
            },
        }
        return self._request("POST", "/databases", json=payload)

    def retrieve_database(self, database_id: str) -> dict[str, object]:
        return self._request("GET", f"/databases/{database_id}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, object]:
        return self._request("GET", f"/data_sources/{data_source_id}")

    def retrieve_page(self, page_id: str) -> dict[str, object]:
        return self._request("GET", f"/pages/{page_id}")

    def archive_page(self, page_id: str) -> dict[str, object]:
        return self._request("PATCH", f"/pages/{page_id}", json={"archived": True})

    def update_page(self, page_id: str, properties: dict[str, object]) -> dict[str, object]:
        return self._request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter: dict[str, object] | None = None,
        sorts: list[dict[str, object]] | None = None,
        start_cursor: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {}
        if filter is not None:
            payload["filter"] = filter
        if sorts is not None:
            payload["sorts"] = sorts
        if start_cursor is not None:
            payload["start_cursor"] = start_cursor
        if page_size is not None:
            payload["page_size"] = page_size
        return self._request("POST", f"/data_sources/{data_source_id}/query", json=payload)

    def search_data_sources_by_title(self, database_title: str) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        start_cursor: str | None = None

        while True:
            payload: dict[str, object] = {
                "query": database_title,
                "page_size": 100,
                "filter": {
                    "property": "object",
                    "value": "data_source",
                },
            }
            if start_cursor:
                payload["start_cursor"] = start_cursor

            page = self._request("POST", "/search", json=payload)
            page_results = page.get("results")
            if isinstance(page_results, list):
                results.extend(item for item in page_results if isinstance(item, dict))

            has_more = page.get("has_more")
            next_cursor = page.get("next_cursor")
            if not has_more or not isinstance(next_cursor, str):
                break
            start_cursor = next_cursor

        return results


def rich_text_to_plain_text(value: object) -> str:
    if not isinstance(value, list):
        return ""

    chunks: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        plain_text = item.get("plain_text")
        if isinstance(plain_text, str):
            chunks.append(plain_text)
    return "".join(chunks)


def iter_database_data_sources(database: dict[str, object]) -> Iterator[dict[str, object]]:
    data_sources = database.get("data_sources")
    if not isinstance(data_sources, list):
        return iter(())
    return (item for item in data_sources if isinstance(item, dict))
