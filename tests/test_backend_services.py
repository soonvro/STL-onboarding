from __future__ import annotations

import unittest

from backend.app.models import InquiryCreateRequest, InquiryStatus, InquiryUpdateRequest
from backend.app.n8n_gateway import N8nWorkflowError
from backend.app.services import (
    DuplicateInquiryError,
    InquiryProcessingError,
    InquiryService,
    IntegrationFailureError,
    compute_dedup_key,
)


class FakeRedisStore:
    def __init__(self, *, acquire_inquiry_lock: bool = True, acquire_page_lock: bool = True) -> None:
        self.inquiry_lock_success = acquire_inquiry_lock
        self.page_lock_success = acquire_page_lock
        self.states: dict[str, dict[str, str]] = {}
        self.page_map: dict[str, str] = {}

    def get_inquiry_state(self, dedup_key: str) -> dict[str, str]:
        return dict(self.states.get(dedup_key, {}))

    def set_inquiry_state(self, dedup_key: str, *, status: str, request_id: str, notion_page_id: str | None = None, error_code: str | None = None) -> None:
        state = {"status": status, "request_id": request_id}
        if notion_page_id:
            state["notion_page_id"] = notion_page_id
        if error_code:
            state["error_code"] = error_code
        self.states[dedup_key] = state

    def record_page_mapping(self, notion_page_id: str, dedup_key: str) -> None:
        self.page_map[notion_page_id] = dedup_key

    def acquire_inquiry_lock(self, dedup_key: str, token: str, *, ttl_seconds: int = 60) -> bool:
        _ = (dedup_key, token, ttl_seconds)
        return self.inquiry_lock_success

    def release_inquiry_lock(self, dedup_key: str, token: str) -> None:
        _ = (dedup_key, token)

    def acquire_page_lock(self, notion_page_id: str, token: str, *, ttl_seconds: int = 30) -> bool:
        _ = (notion_page_id, token, ttl_seconds)
        return self.page_lock_success

    def release_page_lock(self, notion_page_id: str, token: str) -> None:
        _ = (notion_page_id, token)


class FakeNotionGateway:
    def __init__(self, existing_page_id: str | None = None) -> None:
        self.existing_page_id = existing_page_id
        self.inquiry = None
        self.updated = []

    def find_by_dedup_key(self, dedup_key: str) -> str | None:
        _ = dedup_key
        return self.existing_page_id

    def list_inquiries(self, *, status, cursor, page_size):
        _ = (status, cursor, page_size)
        raise NotImplementedError

    def get_inquiry(self, notion_page_id: str):
        _ = notion_page_id
        return self.inquiry

    def update_status(self, notion_page_id: str, *, status, resolution=None):
        _ = notion_page_id
        self.updated.append((status, resolution))
        self.inquiry = type(
            "Inquiry",
            (),
            {
                "id": notion_page_id,
                "name": "홍길동",
                "email": "user@example.com",
                "phone": "010-1234-5678",
                "title": "문의 제목",
                "body": "문의 본문",
                "status": status,
                "resolution": resolution,
                "created_at": "2026-03-23T00:00:00Z",
                "updated_at": "2026-03-23T00:00:01Z",
            },
        )()
        return self.inquiry


class FakeN8nGateway:
    def __init__(self, *, fail_register: bool = False, fail_complete: bool = False) -> None:
        self.fail_register = fail_register
        self.fail_complete = fail_complete

    def register_inquiry(self, payload: dict[str, object]):
        _ = payload
        if self.fail_register:
            raise N8nWorkflowError("register failed")
        return type("RegisterResult", (), {"notion_page_id": "page-1", "admin_email_status": "sent"})()

    def complete_inquiry(self, payload: dict[str, object]):
        _ = payload
        if self.fail_complete:
            raise N8nWorkflowError("complete failed")
        return type(
            "CompleteResult",
            (),
            {
                "notion_page_id": "page-1",
                "requester_email_status": "sent",
                "admin_email_status": "sent",
            },
        )()


class BackendServiceTest(unittest.TestCase):
    def test_compute_dedup_key_normalizes_name_and_title(self) -> None:
        left = compute_dedup_key(" Hong  Gil  Dong ", " Service  Inquiry ")
        right = compute_dedup_key("hong gil dong", "service inquiry")
        self.assertEqual(left, right)

    def test_create_inquiry_rejects_duplicate_when_notion_row_exists(self) -> None:
        service = InquiryService(
            redis_store=FakeRedisStore(),
            notion_gateway=FakeNotionGateway(existing_page_id="page-1"),
            n8n_gateway=FakeN8nGateway(),
            notion_database_id="database-id",
            admin_notification_email="admin@example.com",
        )
        with self.assertRaises(DuplicateInquiryError):
            service.create_inquiry(
                InquiryCreateRequest(
                    name="홍길동",
                    email="user@example.com",
                    phone="010-1234-5678",
                    title="문의 제목",
                    body="문의 본문",
                )
            )

    def test_create_inquiry_marks_failed_when_register_workflow_fails(self) -> None:
        redis_store = FakeRedisStore()
        service = InquiryService(
            redis_store=redis_store,
            notion_gateway=FakeNotionGateway(),
            n8n_gateway=FakeN8nGateway(fail_register=True),
            notion_database_id="database-id",
            admin_notification_email="admin@example.com",
        )
        with self.assertRaises(IntegrationFailureError):
            service.create_inquiry(
                InquiryCreateRequest(
                    name="홍길동",
                    email="user@example.com",
                    phone="010-1234-5678",
                    title="문의 제목",
                    body="문의 본문",
                )
            )
        state = next(iter(redis_store.states.values()))
        self.assertEqual(state["status"], "failed")

    def test_update_inquiry_rejects_concurrent_page_update(self) -> None:
        notion = FakeNotionGateway()
        notion.inquiry = type(
            "Inquiry",
            (),
            {
                "id": "page-1",
                "name": "홍길동",
                "email": "user@example.com",
                "phone": "010-1234-5678",
                "title": "문의 제목",
                "body": "문의 본문",
                "status": InquiryStatus.REGISTERED,
                "resolution": None,
                "created_at": "2026-03-23T00:00:00Z",
                "updated_at": "2026-03-23T00:00:01Z",
            },
        )()
        service = InquiryService(
            redis_store=FakeRedisStore(acquire_page_lock=False),
            notion_gateway=notion,
            n8n_gateway=FakeN8nGateway(),
            notion_database_id="database-id",
            admin_notification_email="admin@example.com",
        )
        with self.assertRaises(InquiryProcessingError):
            service.update_inquiry("page-1", InquiryUpdateRequest(status=InquiryStatus.IN_PROGRESS))
