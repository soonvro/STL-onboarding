from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

import httpx

from automation.envfile import BackendIntegrationTestConfig
from automation.notion_api import NotionClient
from backend.app.models import InquiryStatus


class BackendIntegrationTestError(RuntimeError):
    """Raised when the live backend integration test fails."""


@dataclass(slots=True)
class BackendIntegrationTestResult:
    request_id: str
    notion_page_id: str
    duplicate_code: str
    final_status: str


@dataclass(slots=True)
class BackendIntegrationTestService:
    config: BackendIntegrationTestConfig
    notion_client: NotionClient
    http: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.http = httpx.Client(base_url=self.config.backend_base_url.rstrip("/"), timeout=30.0)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "BackendIntegrationTestService":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def run(self) -> BackendIntegrationTestResult:
        suffix = uuid.uuid4().hex[:10]
        title = f"Backend Integration Inquiry {suffix}"
        body = f"Backend integration body {suffix}"
        resolution = f"Backend integration resolution {suffix}"
        notion_page_id: str | None = None
        request_id = ""

        try:
            self._assert_healthz()
            created = self._create_inquiry(title=title, body=body)
            request_id = _required_string(created, "request_id")
            notion_page_id = _required_string(created, "notion_page_id")

            duplicate_payload = self._assert_duplicate(title=title, body=body)
            duplicate_detail = duplicate_payload.get("detail")
            if not isinstance(duplicate_detail, dict):
                raise BackendIntegrationTestError("Duplicate response did not include detail object")
            duplicate_code = _required_string(duplicate_detail, "code")

            self._login_admin()
            self._assert_admin_list_contains(notion_page_id)
            self._assert_admin_detail(notion_page_id)
            self._assert_status_update(notion_page_id, InquiryStatus.IN_PROGRESS)
            self._assert_status_update(notion_page_id, InquiryStatus.COMPLETED, resolution=resolution)
            self._wait_for_notion_completion(notion_page_id, expected_resolution=resolution)

            return BackendIntegrationTestResult(
                request_id=request_id,
                notion_page_id=notion_page_id,
                duplicate_code=duplicate_code,
                final_status=InquiryStatus.COMPLETED.value,
            )
        finally:
            if notion_page_id:
                try:
                    self.notion_client.archive_page(notion_page_id)
                except Exception:
                    pass

    def _assert_healthz(self) -> None:
        response = self.http.get("/healthz")
        if response.status_code == 200:
            return

        fallback = self.http.get("/")
        if fallback.status_code == 200:
            return

        raise BackendIntegrationTestError(
            f"GET /healthz returned {response.status_code}: {response.text}"
        )

    def _create_inquiry(self, *, title: str, body: str) -> dict[str, object]:
        response = self.http.post(
            "/api/v1/inquiries",
            json={
                "name": "Backend Integration",
                "email": self.config.requester_email,
                "phone": "010-0000-0000",
                "title": title,
                "body": body,
            },
        )
        if response.status_code != 201:
            raise BackendIntegrationTestError(
                f"POST /api/v1/inquiries returned {response.status_code}: {response.text}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise BackendIntegrationTestError("Create inquiry response was not a JSON object")
        return payload

    def _assert_duplicate(self, *, title: str, body: str) -> dict[str, object]:
        response = self.http.post(
            "/api/v1/inquiries",
            json={
                "name": "Backend Integration",
                "email": self.config.requester_email,
                "phone": "010-0000-0000",
                "title": title,
                "body": body,
            },
        )
        if response.status_code != 409:
            raise BackendIntegrationTestError(
                f"Duplicate create returned {response.status_code}: {response.text}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise BackendIntegrationTestError("Duplicate response was not a JSON object")
        return payload

    def _login_admin(self) -> None:
        response = self.http.post("/api/v1/admin/session", json={"password": self.config.admin_password})
        if response.status_code != 200:
            raise BackendIntegrationTestError(
                f"POST /api/v1/admin/session returned {response.status_code}: {response.text}"
            )

    def _assert_admin_list_contains(self, notion_page_id: str) -> None:
        response = self.http.get("/api/v1/admin/inquiries", params={"status": InquiryStatus.REGISTERED.value})
        if response.status_code != 200:
            raise BackendIntegrationTestError(
                f"GET /api/v1/admin/inquiries returned {response.status_code}: {response.text}"
            )
        payload = response.json()
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not any(
            isinstance(item, dict) and item.get("id") == notion_page_id for item in items
        ):
            raise BackendIntegrationTestError("Created inquiry was not found in the admin list")

    def _assert_admin_detail(self, notion_page_id: str) -> None:
        response = self.http.get(f"/api/v1/admin/inquiries/{notion_page_id}")
        if response.status_code != 200:
            raise BackendIntegrationTestError(
                f"GET /api/v1/admin/inquiries/{{id}} returned {response.status_code}: {response.text}"
            )

    def _assert_status_update(self, notion_page_id: str, status: InquiryStatus, *, resolution: str | None = None) -> None:
        payload: dict[str, object] = {"status": status.value}
        if resolution is not None:
            payload["resolution"] = resolution
        response = self.http.patch(f"/api/v1/admin/inquiries/{notion_page_id}", json=payload)
        if response.status_code != 200:
            raise BackendIntegrationTestError(
                f"PATCH {status.value} returned {response.status_code}: {response.text}"
            )

    def _wait_for_notion_completion(self, notion_page_id: str, *, expected_resolution: str) -> None:
        deadline = time.monotonic() + 20.0
        while True:
            page = self.notion_client.retrieve_page(notion_page_id)
            properties = page.get("properties")
            if isinstance(properties, dict):
                status_obj = properties.get("Status")
                resolution_obj = properties.get("Resolution")
                status_name = ""
                resolution_text = ""
                if isinstance(status_obj, dict):
                    status = status_obj.get("status")
                    if isinstance(status, dict):
                        status_name = status.get("name") if isinstance(status.get("name"), str) else ""
                if isinstance(resolution_obj, dict):
                    rich_text = resolution_obj.get("rich_text")
                    if isinstance(rich_text, list):
                        resolution_text = "".join(
                            item.get("plain_text", "") for item in rich_text if isinstance(item, dict)
                        )
                if status_name == "Completed" and resolution_text == expected_resolution:
                    return
            if time.monotonic() >= deadline:
                raise BackendIntegrationTestError(
                    f"Timed out waiting for Notion page {notion_page_id} to reflect completed status"
                )
            time.sleep(1.0)


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BackendIntegrationTestError(f"Response is missing a non-empty string field: {key}")
    return value
