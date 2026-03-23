from __future__ import annotations

from dataclasses import dataclass

from automation.notion_api import NotionApiError, NotionClient, rich_text_to_plain_text
from automation.notion_schema import (
    BODY_PROPERTY_NAME,
    CREATED_AT_PROPERTY_NAME,
    DEDUP_KEY_PROPERTY_NAME,
    EMAIL_PROPERTY_NAME,
    NAME_PROPERTY_NAME,
    PHONE_PROPERTY_NAME,
    RESOLUTION_PROPERTY_NAME,
    STATUS_NAME_MAPPING,
    STATUS_PROPERTY_NAME,
    TITLE_PROPERTY_NAME,
    UPDATED_AT_PROPERTY_NAME,
)

from backend.app.models import InquiryDetailResponse, InquiryListItem, InquiryStatus


NOTION_TO_API_STATUS = {value: key for key, value in STATUS_NAME_MAPPING.items()}


class InquiryNotFoundError(RuntimeError):
    """Raised when the requested inquiry does not exist in Notion."""


@dataclass(slots=True)
class InquiryListPage:
    items: list[InquiryListItem]
    next_cursor: str | None


@dataclass(slots=True)
class NotionInquiryGateway:
    client: NotionClient
    data_source_id: str

    def close(self) -> None:
        self.client.close()

    def list_inquiries(
        self,
        *,
        status: InquiryStatus | None,
        cursor: str | None,
        page_size: int,
    ) -> InquiryListPage:
        filter_payload = None
        if status is not None:
            filter_payload = {
                "property": STATUS_PROPERTY_NAME,
                "status": {"equals": STATUS_NAME_MAPPING[status.value]},
            }

        payload = self.client.query_data_source(
            self.data_source_id,
            filter=filter_payload,
            sorts=[{"property": CREATED_AT_PROPERTY_NAME, "direction": "descending"}],
            start_cursor=cursor,
            page_size=page_size,
        )

        results = payload.get("results")
        items = []
        if isinstance(results, list):
            items = [self._to_list_item(page) for page in results if isinstance(page, dict)]
        next_cursor = payload.get("next_cursor")
        return InquiryListPage(items=items, next_cursor=next_cursor if isinstance(next_cursor, str) else None)

    def get_inquiry(self, notion_page_id: str) -> InquiryDetailResponse:
        try:
            page = self.client.retrieve_page(notion_page_id)
        except NotionApiError as exc:
            if exc.status_code == 404:
                raise InquiryNotFoundError("inquiry not found") from exc
            raise
        return self._to_detail(page)

    def find_by_dedup_key(self, dedup_key: str) -> str | None:
        payload = self.client.query_data_source(
            self.data_source_id,
            filter={
                "property": DEDUP_KEY_PROPERTY_NAME,
                "rich_text": {"equals": dedup_key},
            },
            page_size=1,
        )
        results = payload.get("results")
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    page_id = item.get("id")
                    if isinstance(page_id, str):
                        return page_id
        return None

    def update_status(self, notion_page_id: str, *, status: InquiryStatus, resolution: str | None = None) -> InquiryDetailResponse:
        properties: dict[str, object] = {
            STATUS_PROPERTY_NAME: {"status": {"name": STATUS_NAME_MAPPING[status.value]}},
        }
        if resolution is not None:
            properties[RESOLUTION_PROPERTY_NAME] = {"rich_text": _rich_text(resolution)}
        page = self.client.update_page(notion_page_id, properties)
        return self._to_detail(page)

    def _to_list_item(self, page: dict[str, object]) -> InquiryListItem:
        properties = _properties(page)
        return InquiryListItem(
            id=_string(page.get("id")),
            name=_rich_text_property(properties, NAME_PROPERTY_NAME),
            email=_email_property(properties, EMAIL_PROPERTY_NAME),
            phone=_phone_property(properties, PHONE_PROPERTY_NAME),
            title=_title_property(properties, TITLE_PROPERTY_NAME),
            status=_status_property(properties, STATUS_PROPERTY_NAME),
            created_at=_created_time_property(page, properties, CREATED_AT_PROPERTY_NAME),
        )

    def _to_detail(self, page: dict[str, object]) -> InquiryDetailResponse:
        properties = _properties(page)
        return InquiryDetailResponse(
            id=_string(page.get("id")),
            name=_rich_text_property(properties, NAME_PROPERTY_NAME),
            email=_email_property(properties, EMAIL_PROPERTY_NAME),
            phone=_phone_property(properties, PHONE_PROPERTY_NAME),
            title=_title_property(properties, TITLE_PROPERTY_NAME),
            body=_rich_text_property(properties, BODY_PROPERTY_NAME),
            status=_status_property(properties, STATUS_PROPERTY_NAME),
            resolution=_optional_rich_text_property(properties, RESOLUTION_PROPERTY_NAME),
            created_at=_created_time_property(page, properties, CREATED_AT_PROPERTY_NAME),
            updated_at=_updated_time_property(page, properties, UPDATED_AT_PROPERTY_NAME),
        )


def _properties(page: dict[str, object]) -> dict[str, dict[str, object]]:
    properties = page.get("properties")
    if not isinstance(properties, dict):
        raise InquiryNotFoundError("page properties missing")
    return {str(key): value for key, value in properties.items() if isinstance(value, dict)}


def _string(value: object) -> str:
    if isinstance(value, str):
        return value
    raise InquiryNotFoundError("missing string field")


def _title_property(properties: dict[str, dict[str, object]], key: str) -> str:
    return rich_text_to_plain_text(properties.get(key, {}).get("title"))


def _rich_text_property(properties: dict[str, dict[str, object]], key: str) -> str:
    return rich_text_to_plain_text(properties.get(key, {}).get("rich_text"))


def _optional_rich_text_property(properties: dict[str, dict[str, object]], key: str) -> str | None:
    value = _rich_text_property(properties, key)
    return value or None


def _email_property(properties: dict[str, dict[str, object]], key: str) -> str:
    value = properties.get(key, {}).get("email")
    return value if isinstance(value, str) else ""


def _phone_property(properties: dict[str, dict[str, object]], key: str) -> str:
    value = properties.get(key, {}).get("phone_number")
    return value if isinstance(value, str) else ""


def _status_property(properties: dict[str, dict[str, object]], key: str) -> InquiryStatus:
    status_obj = properties.get(key, {}).get("status")
    name = status_obj.get("name") if isinstance(status_obj, dict) else None
    if not isinstance(name, str) or name not in NOTION_TO_API_STATUS:
        raise InquiryNotFoundError("status property missing")
    return InquiryStatus(NOTION_TO_API_STATUS[name])


def _created_time_property(page: dict[str, object], properties: dict[str, dict[str, object]], key: str) -> str:
    prop = properties.get(key, {}).get("created_time")
    if isinstance(prop, str):
        return prop
    return _string(page.get("created_time"))


def _updated_time_property(page: dict[str, object], properties: dict[str, dict[str, object]], key: str) -> str:
    prop = properties.get(key, {}).get("last_edited_time")
    if isinstance(prop, str):
        return prop
    return _string(page.get("last_edited_time"))


def _rich_text(value: str) -> list[dict[str, object]]:
    return [{"type": "text", "text": {"content": value}}]
