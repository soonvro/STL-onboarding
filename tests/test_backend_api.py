from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.auth import AdminAuthService
from backend.app.dependencies import AppContainer
from backend.app.main import create_app
from backend.app.models import InquiryCreateRequest, InquiryDetailResponse, InquiryListItem, InquiryStatus
from backend.app.notion_gateway import InquiryNotFoundError
from backend.app.settings import AppSettings
from backend.app.services import DuplicateInquiryError, IntegrationFailureError, UpdateProcessingError


class FakeInquiryService:
    def __init__(self) -> None:
        self.created_payloads: list[InquiryCreateRequest] = []
        self.create_error: Exception | None = None
        self.get_error: Exception | None = None
        self.update_error: Exception | None = None

    def create_inquiry(self, request: InquiryCreateRequest):
        if self.create_error is not None:
            raise self.create_error
        self.created_payloads.append(request)
        return type(
            "Result",
            (),
            {
                "request_id": "req-1",
                "notion_page_id": "page-1",
                "admin_email_status": "sent",
            },
        )()

    def list_inquiries(self, *, status, cursor, page_size):
        _ = (status, cursor, page_size)
        return type(
            "Page",
            (),
            {
                "items": [
                    InquiryListItem(
                        id="page-1",
                        name="홍길동",
                        email="user@example.com",
                        phone="010-1234-5678",
                        title="문의 제목",
                        status=InquiryStatus.REGISTERED,
                        created_at="2026-03-23T00:00:00Z",
                    )
                ],
                "next_cursor": None,
            },
        )()

    def get_inquiry(self, notion_page_id: str) -> InquiryDetailResponse:
        if self.get_error is not None:
            raise self.get_error
        _ = notion_page_id
        return InquiryDetailResponse(
            id="page-1",
            name="홍길동",
            email="user@example.com",
            phone="010-1234-5678",
            title="문의 제목",
            body="본문",
            status=InquiryStatus.REGISTERED,
            resolution=None,
            created_at="2026-03-23T00:00:00Z",
            updated_at="2026-03-23T00:00:00Z",
        )

    def update_inquiry(self, notion_page_id: str, request):
        if self.update_error is not None:
            raise self.update_error
        _ = (notion_page_id, request)
        return type("UpdateResult", (), {"inquiry": self.get_inquiry("page-1")})()


class BackendApiTest(unittest.TestCase):
    def make_client(self, inquiry_service: FakeInquiryService | None = None) -> TestClient:
        env = {
            "ADMIN_PASSWORD": "secret",
            "ADMIN_JWT_SECRET": "jwt-secret-0123456789abcdef01234567",
            "ADMIN_COOKIE_SECURE": "false",
            "BACKEND_ALLOWED_ORIGINS": '["http://localhost:3000"]',
            "REDIS_URL": "redis://localhost:6379/0",
            "NOTION_TOKEN": "notion-token",
            "NOTION_DATABASE_ID": "database-id",
            "NOTION_DATA_SOURCE_ID": "data-source-id",
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_SHARED_SECRET": "shared-secret",
            "N8N_WEBHOOK_REGISTER_PATH": "register",
            "N8N_WEBHOOK_COMPLETE_PATH": "complete",
            "ADMIN_NOTIFICATION_EMAIL": "admin@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = AppSettings(_env_file=None)
        inquiry_service = inquiry_service or FakeInquiryService()
        container = AppContainer(
            settings=settings,
            auth_service=AdminAuthService("jwt-secret-0123456789abcdef01234567", 60),
            inquiry_service=inquiry_service,
            closeables=[],
        )
        return TestClient(create_app(settings=settings, container=container))

    def test_public_inquiry_endpoint_returns_created_payload(self) -> None:
        client = self.make_client()
        response = client.post(
            "/api/v1/inquiries",
            json={
                "name": "홍길동",
                "email": "user@example.com",
                "phone": "010-1234-5678",
                "title": "문의 제목",
                "body": "문의 본문",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["request_id"], "req-1")

    def test_public_inquiry_endpoint_translates_duplicate_error_to_409(self) -> None:
        service = FakeInquiryService()
        service.create_error = DuplicateInquiryError("이미 등록된 문의입니다.")
        client = self.make_client(service)

        response = client.post(
            "/api/v1/inquiries",
            json={
                "name": "홍길동",
                "email": "user@example.com",
                "phone": "010-1234-5678",
                "title": "문의 제목",
                "body": "문의 본문",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "duplicate_inquiry")
        self.assertEqual(response.json()["detail"]["message"], "이미 등록된 문의입니다.")

    def test_root_endpoint_returns_service_status(self) -> None:
        client = self.make_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"service": "qna-backend", "status": "ok"})

    def test_admin_session_cookie_auth_flow(self) -> None:
        client = self.make_client()
        login = client.post("/api/v1/admin/session", json={"password": "secret"})
        self.assertEqual(login.status_code, 200)
        self.assertIn("admin_session", client.cookies)

        session = client.get("/api/v1/admin/session")
        self.assertEqual(session.status_code, 200)
        self.assertTrue(session.json()["authenticated"])

        inquiry_list = client.get("/api/v1/admin/inquiries")
        self.assertEqual(inquiry_list.status_code, 200)
        self.assertEqual(len(inquiry_list.json()["items"]), 1)

    def test_admin_inquiry_list_requires_session(self) -> None:
        client = self.make_client()
        response = client.get("/api/v1/admin/inquiries")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "admin session required")

    def test_get_inquiry_returns_not_found_detail(self) -> None:
        service = FakeInquiryService()
        service.get_error = InquiryNotFoundError("inquiry not found")
        client = self.make_client(service)

        login = client.post("/api/v1/admin/session", json={"password": "secret"})
        self.assertEqual(login.status_code, 200)

        response = client.get("/api/v1/admin/inquiries/page-missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "inquiry not found")

    def test_update_inquiry_translates_processing_error_code(self) -> None:
        service = FakeInquiryService()
        service.update_error = UpdateProcessingError("상태 변경이 처리 중입니다. 잠시 후 다시 시도해주세요.")
        client = self.make_client(service)

        login = client.post("/api/v1/admin/session", json={"password": "secret"})
        self.assertEqual(login.status_code, 200)

        response = client.patch(
            "/api/v1/admin/inquiries/page-1",
            json={"status": InquiryStatus.IN_PROGRESS.value},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "update_processing")

    def test_update_inquiry_translates_integration_failure_to_502(self) -> None:
        service = FakeInquiryService()
        service.update_error = IntegrationFailureError("문의 완료 워크플로우 호출에 실패했습니다.")
        client = self.make_client(service)

        login = client.post("/api/v1/admin/session", json={"password": "secret"})
        self.assertEqual(login.status_code, 200)

        response = client.patch(
            "/api/v1/admin/inquiries/page-1",
            json={"status": InquiryStatus.COMPLETED.value, "resolution": "답변 완료"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["code"], "integration_failure")
