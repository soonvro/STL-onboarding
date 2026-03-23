from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class N8nWorkflowError(RuntimeError):
    """Raised when an n8n workflow call fails."""


@dataclass(slots=True)
class RegisterWorkflowResult:
    notion_page_id: str
    admin_email_status: str


@dataclass(slots=True)
class CompleteWorkflowResult:
    notion_page_id: str
    requester_email_status: str
    admin_email_status: str


@dataclass(slots=True)
class N8nWorkflowGateway:
    base_url: str
    shared_secret: str
    register_path: str
    complete_path: str
    timeout_seconds: float = 30.0
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(timeout=self.timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def register_inquiry(self, payload: dict[str, object]) -> RegisterWorkflowResult:
        data = self._call(self.register_path, payload)
        notion_page_id = data.get("notion_page_id")
        admin_email_status = data.get("admin_email_status")
        if not isinstance(notion_page_id, str) or not notion_page_id:
            raise N8nWorkflowError("register workflow did not return notion_page_id")
        if not isinstance(admin_email_status, str) or not admin_email_status:
            raise N8nWorkflowError("register workflow did not return admin_email_status")
        return RegisterWorkflowResult(notion_page_id=notion_page_id, admin_email_status=admin_email_status)

    def complete_inquiry(self, payload: dict[str, object]) -> CompleteWorkflowResult:
        data = self._call(self.complete_path, payload)
        notion_page_id = data.get("notion_page_id")
        requester_email_status = data.get("requester_email_status")
        admin_email_status = data.get("admin_email_status")
        if not isinstance(notion_page_id, str) or not notion_page_id:
            raise N8nWorkflowError("complete workflow did not return notion_page_id")
        if not isinstance(requester_email_status, str) or not requester_email_status:
            raise N8nWorkflowError("complete workflow did not return requester_email_status")
        if not isinstance(admin_email_status, str) or not admin_email_status:
            raise N8nWorkflowError("complete workflow did not return admin_email_status")
        return CompleteWorkflowResult(
            notion_page_id=notion_page_id,
            requester_email_status=requester_email_status,
            admin_email_status=admin_email_status,
        )

    def _call(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        url = f"{self.base_url.rstrip('/')}/webhook/{path.lstrip('/')}"
        response = self._client.post(url, json=payload, headers={"X-N8N-Shared-Secret": self.shared_secret})
        if not response.is_success:
            raise N8nWorkflowError(f"workflow call failed with {response.status_code}: {response.text}")
        try:
            data = response.json()
        except ValueError as exc:
            raise N8nWorkflowError("workflow returned a non-JSON response") from exc
        if not isinstance(data, dict):
            raise N8nWorkflowError("workflow returned a non-object JSON response")
        if data.get("status") != "ok":
            raise N8nWorkflowError(f"workflow returned status={data.get('status')!r}")
        return data
