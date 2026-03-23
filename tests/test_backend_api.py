from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.auth import AdminAuthService
from backend.app.dependencies import AppContainer
from backend.app.main import create_app
from backend.app.models import InquiryCreateRequest, InquiryDetailResponse, InquiryListItem, InquiryStatus
from backend.app.settings import AppSettings


class FakeInquiryService:
    def __init__(self) -> None:
        self.created_payloads: list[InquiryCreateRequest] = []

    def create_inquiry(self, request: InquiryCreateRequest):
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
        _ = (notion_page_id, request)
        return type("UpdateResult", (), {"inquiry": self.get_inquiry("page-1")})()


class BackendApiTest(unittest.TestCase):
    def make_client(self) -> TestClient:
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
        container = AppContainer(
            settings=settings,
            auth_service=AdminAuthService("jwt-secret-0123456789abcdef01234567", 60),
            inquiry_service=FakeInquiryService(),
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
