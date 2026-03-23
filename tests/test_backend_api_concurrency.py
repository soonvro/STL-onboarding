from __future__ import annotations

import asyncio
import os
import threading
import time
import unittest
from unittest.mock import patch

import httpx

from backend.app.auth import AdminAuthService
from backend.app.dependencies import AppContainer
from backend.app.main import create_app
from backend.app.services import InquiryService
from backend.app.settings import AppSettings


class ThreadSafeRedisStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.states: dict[str, dict[str, str]] = {}
        self.inquiry_locks: dict[str, str] = {}
        self.page_locks: dict[str, str] = {}
        self.page_map: dict[str, str] = {}

    def close(self) -> None:
        return None

    def get_inquiry_state(self, dedup_key: str) -> dict[str, str]:
        with self._lock:
            return dict(self.states.get(dedup_key, {}))

    def set_inquiry_state(
        self,
        dedup_key: str,
        *,
        status: str,
        request_id: str,
        notion_page_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        state = {"status": status, "request_id": request_id}
        if notion_page_id:
            state["notion_page_id"] = notion_page_id
        if error_code:
            state["error_code"] = error_code
        with self._lock:
            self.states[dedup_key] = state

    def record_page_mapping(self, notion_page_id: str, dedup_key: str) -> None:
        with self._lock:
            self.page_map[notion_page_id] = dedup_key

    def acquire_inquiry_lock(self, dedup_key: str, token: str, *, ttl_seconds: int = 60) -> bool:
        _ = ttl_seconds
        with self._lock:
            if dedup_key in self.inquiry_locks:
                return False
            self.inquiry_locks[dedup_key] = token
            return True

    def release_inquiry_lock(self, dedup_key: str, token: str) -> None:
        with self._lock:
            if self.inquiry_locks.get(dedup_key) == token:
                del self.inquiry_locks[dedup_key]

    def acquire_page_lock(self, notion_page_id: str, token: str, *, ttl_seconds: int = 30) -> bool:
        _ = ttl_seconds
        with self._lock:
            if notion_page_id in self.page_locks:
                return False
            self.page_locks[notion_page_id] = token
            return True

    def release_page_lock(self, notion_page_id: str, token: str) -> None:
        with self._lock:
            if self.page_locks.get(notion_page_id) == token:
                del self.page_locks[notion_page_id]


class ConcurrencyAwareNotionGateway:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.existing_by_dedup_key: dict[str, str] = {}

    def close(self) -> None:
        return None

    def find_by_dedup_key(self, dedup_key: str) -> str | None:
        with self._lock:
            return self.existing_by_dedup_key.get(dedup_key)

    def mark_existing(self, dedup_key: str, notion_page_id: str) -> None:
        with self._lock:
            self.existing_by_dedup_key[dedup_key] = notion_page_id

    def list_inquiries(self, *, status, cursor, page_size):
        _ = (status, cursor, page_size)
        raise NotImplementedError

    def get_inquiry(self, notion_page_id: str):
        _ = notion_page_id
        raise NotImplementedError


class SlowRegisterN8nGateway:
    def __init__(self, notion_gateway: ConcurrencyAwareNotionGateway, *, delay_seconds: float = 0.05) -> None:
        self.notion_gateway = notion_gateway
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self.register_payloads: list[object] = []

    def close(self) -> None:
        return None

    def register_inquiry(self, payload):
        with self._lock:
            self.register_payloads.append(payload)
            call_index = len(self.register_payloads)
        time.sleep(self.delay_seconds)
        notion_page_id = f"page-{call_index}"
        self.notion_gateway.mark_existing(payload.dedup_key, notion_page_id)
        return type(
            "RegisterResult",
            (),
            {
                "notion_page_id": notion_page_id,
                "admin_email_status": "sent",
            },
        )()

    def complete_inquiry(self, payload):
        _ = payload
        raise NotImplementedError


class BackendApiConcurrencyTest(unittest.IsolatedAsyncioTestCase):
    def make_app(self) -> tuple[object, SlowRegisterN8nGateway]:
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

        redis_store = ThreadSafeRedisStore()
        notion_gateway = ConcurrencyAwareNotionGateway()
        n8n_gateway = SlowRegisterN8nGateway(notion_gateway, delay_seconds=0.05)
        inquiry_service = InquiryService(
            redis_store=redis_store,
            notion_gateway=notion_gateway,
            n8n_gateway=n8n_gateway,
            notion_database_id="database-id",
            admin_notification_email="admin@example.com",
            inquiry_lock_retry_attempts=20,
            inquiry_lock_retry_delay_seconds=0.01,
        )
        container = AppContainer(
            settings=settings,
            auth_service=AdminAuthService("jwt-secret-0123456789abcdef01234567", 60),
            inquiry_service=inquiry_service,
            closeables=[],
        )
        return create_app(settings=settings, container=container), n8n_gateway

    async def test_concurrent_identical_inquiries_trigger_single_register_workflow(self) -> None:
        app, n8n_gateway = self.make_app()
        transport = httpx.ASGITransport(app=app)
        payload = {
            "name": "홍길동",
            "email": "user@example.com",
            "phone": "010-1234-5678",
            "title": "문의 제목",
            "body": "문의 본문",
        }

        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            responses = await asyncio.gather(
                client.post("/api/v1/inquiries", json=payload),
                client.post("/api/v1/inquiries", json=payload),
            )

        status_codes = sorted(response.status_code for response in responses)
        self.assertEqual(status_codes, [201, 409])

        success_response = next(response for response in responses if response.status_code == 201)
        duplicate_response = next(response for response in responses if response.status_code == 409)

        self.assertTrue(success_response.json()["request_id"].startswith("req-"))
        self.assertEqual(duplicate_response.json()["detail"]["code"], "duplicate_inquiry")
        self.assertEqual(len(n8n_gateway.register_payloads), 1)


if __name__ == "__main__":
    unittest.main()
