from __future__ import annotations

import unittest

from automation.notion_api import NotionApiError
from automation.notion_schema import (
    BODY_PROPERTY_NAME,
    CREATED_AT_PROPERTY_NAME,
    EMAIL_PROPERTY_NAME,
    NAME_PROPERTY_NAME,
    PHONE_PROPERTY_NAME,
    RESOLUTION_PROPERTY_NAME,
    STATUS_NAME_MAPPING,
    STATUS_PROPERTY_NAME,
    TITLE_PROPERTY_NAME,
    UPDATED_AT_PROPERTY_NAME,
)
from backend.app.models import InquiryStatus
from backend.app.notion_gateway import InquiryNotFoundError, NotionInquiryGateway


def _rich_text(value: str) -> list[dict[str, str]]:
    return [{"plain_text": value}]


def make_page(
    *,
    status_name: str = "Registered",
    include_status: bool = True,
) -> dict[str, object]:
    properties: dict[str, object] = {
        TITLE_PROPERTY_NAME: {"title": _rich_text("문의 제목")},
        NAME_PROPERTY_NAME: {"rich_text": _rich_text("홍길동")},
        EMAIL_PROPERTY_NAME: {"email": "user@example.com"},
        PHONE_PROPERTY_NAME: {"phone_number": "010-1234-5678"},
        BODY_PROPERTY_NAME: {"rich_text": _rich_text("문의 본문")},
        RESOLUTION_PROPERTY_NAME: {"rich_text": _rich_text("답변 완료")},
        CREATED_AT_PROPERTY_NAME: {"created_time": "2026-03-23T00:00:00Z"},
        UPDATED_AT_PROPERTY_NAME: {"last_edited_time": "2026-03-23T00:00:01Z"},
    }
    if include_status:
        properties[STATUS_PROPERTY_NAME] = {"status": {"name": status_name}}

    return {
        "id": "page-1",
        "created_time": "2026-03-23T00:00:00Z",
        "last_edited_time": "2026-03-23T00:00:01Z",
        "properties": properties,
    }


class FakeNotionClient:
    def __init__(self) -> None:
        self.query_response: dict[str, object] = {"results": [], "next_cursor": None}
        self.page_response: dict[str, object] = make_page()
        self.query_calls: list[dict[str, object]] = []
        self.update_calls: list[dict[str, object]] = []

    def close(self) -> None:
        return None

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter: dict[str, object] | None = None,
        sorts: list[dict[str, object]] | None = None,
        start_cursor: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, object]:
        self.query_calls.append(
            {
                "data_source_id": data_source_id,
                "filter": filter,
                "sorts": sorts,
                "start_cursor": start_cursor,
                "page_size": page_size,
            }
        )
        return self.query_response

    def retrieve_page(self, page_id: str) -> dict[str, object]:
        _ = page_id
        if isinstance(self.page_response, Exception):
            raise self.page_response
        return self.page_response

    def update_page(self, page_id: str, properties: dict[str, object]) -> dict[str, object]:
        self.update_calls.append({"page_id": page_id, "properties": properties})
        return make_page(status_name="In Progress")


class BackendNotionGatewayTest(unittest.TestCase):
    def test_list_inquiries_maps_status_and_uses_shared_property_names(self) -> None:
        client = FakeNotionClient()
        client.query_response = {"results": [make_page(status_name="Registered")], "next_cursor": "cursor-2"}
        gateway = NotionInquiryGateway(client, "data-source-id")

        page = gateway.list_inquiries(
            status=InquiryStatus.REGISTERED,
            cursor="cursor-1",
            page_size=10,
        )

        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].status, InquiryStatus.REGISTERED)
        self.assertEqual(page.next_cursor, "cursor-2")
        self.assertEqual(client.query_calls[0]["filter"], {"property": STATUS_PROPERTY_NAME, "status": {"equals": "Registered"}})
        self.assertEqual(client.query_calls[0]["sorts"], [{"property": CREATED_AT_PROPERTY_NAME, "direction": "descending"}])

    def test_get_inquiry_converts_404_api_errors(self) -> None:
        client = FakeNotionClient()
        client.page_response = NotionApiError("not found", status_code=404)
        gateway = NotionInquiryGateway(client, "data-source-id")

        with self.assertRaises(InquiryNotFoundError):
            gateway.get_inquiry("page-missing")

    def test_get_inquiry_rejects_missing_required_status_property(self) -> None:
        client = FakeNotionClient()
        client.page_response = make_page(include_status=False)
        gateway = NotionInquiryGateway(client, "data-source-id")

        with self.assertRaises(InquiryNotFoundError):
            gateway.get_inquiry("page-1")

    def test_update_status_writes_shared_status_property_name(self) -> None:
        client = FakeNotionClient()
        gateway = NotionInquiryGateway(client, "data-source-id")

        updated = gateway.update_status("page-1", status=InquiryStatus.IN_PROGRESS, resolution="처리 시작")

        self.assertEqual(updated.status, InquiryStatus.IN_PROGRESS)
        self.assertEqual(
            client.update_calls[0]["properties"][STATUS_PROPERTY_NAME],
            {"status": {"name": STATUS_NAME_MAPPING[InquiryStatus.IN_PROGRESS.value]}},
        )
        self.assertIn(RESOLUTION_PROPERTY_NAME, client.update_calls[0]["properties"])


if __name__ == "__main__":
    unittest.main()
