from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from automation.envfile import N8nIntegrationTestConfig
from automation.notion_api import NotionClient, rich_text_to_plain_text


class N8nIntegrationTestError(RuntimeError):
    """Raised when the n8n workflow integration test fails."""


@dataclass(slots=True)
class N8nIntegrationTestResult:
    register_request_id: str
    complete_request_id: str
    notion_page_id: str
    admin_email_status: str
    requester_email_status: str


class N8nIntegrationTestService:
    def __init__(self, config: N8nIntegrationTestConfig, notion_client: NotionClient) -> None:
        self.config = config
        self.notion_client = notion_client
        self.http = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "N8nIntegrationTestService":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def run(self) -> N8nIntegrationTestResult:
        suffix = uuid.uuid4().hex[:10]
        register_request_id = f"it-register-{suffix}"
        complete_request_id = f"it-complete-{suffix}"
        requester_name = "Integration Test"
        title = f"Integration Test Inquiry {suffix}"
        body = f"Integration test body {suffix}"
        resolution = f"Integration test resolution {suffix}"
        dedup_key = hashlib.sha256(f"integration:{suffix}:{title}".encode("utf-8")).hexdigest()
        notion_page_id: str | None = None

        try:
            register_response = self._post_webhook(
                webhook_path=self.config.n8n_webhook_register_path,
                payload={
                    "request_id": register_request_id,
                    "dedup_key": dedup_key,
                    "name": requester_name,
                    "email": self.config.requester_email,
                    "phone": "010-0000-0000",
                    "title": title,
                    "body": body,
                    "admin_email": self.config.admin_email,
                    "notion_database_id": self.config.notion_database_id,
                },
                expected_workflow="inquiry_register",
            )

            notion_page_id = self._required_string(register_response, "notion_page_id")
            admin_email_status = self._required_string(register_response, "admin_email_status")
            if admin_email_status != "sent":
                raise N8nIntegrationTestError(
                    f"Register workflow reported admin_email_status={admin_email_status}"
                )

            self._wait_for_page_registration(
                notion_page_id=notion_page_id,
                expected_title=title,
                expected_dedup_key=dedup_key,
            )

            complete_response = self._post_webhook(
                webhook_path=self.config.n8n_webhook_complete_path,
                payload={
                    "request_id": complete_request_id,
                    "notion_page_id": notion_page_id,
                    "name": requester_name,
                    "title": title,
                    "resolution": resolution,
                    "requester_email": self.config.requester_email,
                    "admin_email": self.config.admin_email,
                },
                expected_workflow="inquiry_complete",
            )

            requester_email_status = self._required_string(complete_response, "requester_email_status")
            admin_completion_status = self._required_string(complete_response, "admin_email_status")
            if requester_email_status != "sent":
                raise N8nIntegrationTestError(
                    f"Complete workflow reported requester_email_status={requester_email_status}"
                )
            if admin_completion_status != "sent":
                raise N8nIntegrationTestError(
                    f"Complete workflow reported admin_email_status={admin_completion_status}"
                )

            self._wait_for_page_completion(
                notion_page_id=notion_page_id,
                expected_resolution=resolution,
            )

            return N8nIntegrationTestResult(
                register_request_id=register_request_id,
                complete_request_id=complete_request_id,
                notion_page_id=notion_page_id,
                admin_email_status=admin_completion_status,
                requester_email_status=requester_email_status,
            )
        finally:
            if notion_page_id:
                try:
                    self.notion_client.archive_page(notion_page_id)
                except Exception:
                    pass

    def _post_webhook(
        self,
        *,
        webhook_path: str,
        payload: dict[str, object],
        expected_workflow: str,
    ) -> dict[str, object]:
        response = self.http.post(
            self._webhook_url(webhook_path),
            headers={"X-N8N-Shared-Secret": self.config.n8n_shared_secret},
            json=payload,
        )

        if response.status_code != 200:
            raise N8nIntegrationTestError(
                f"Webhook {webhook_path} returned {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            snippet = response.text.strip().replace("\n", " ")
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            raise N8nIntegrationTestError(
                f"Webhook {webhook_path} did not return JSON. Response body: {snippet or '<empty>'}"
            ) from exc

        if not isinstance(data, dict):
            raise N8nIntegrationTestError(f"Webhook {webhook_path} returned a non-object JSON payload")

        if data.get("status") != "ok":
            raise N8nIntegrationTestError(f"Webhook {webhook_path} returned status={data.get('status')!r}")
        if data.get("workflow") != expected_workflow:
            raise N8nIntegrationTestError(
                f"Webhook {webhook_path} returned workflow={data.get('workflow')!r}, expected {expected_workflow!r}"
            )

        return data

    def _webhook_url(self, webhook_path: str) -> str:
        return f"{self.config.n8n_base_url.rstrip('/')}/webhook/{webhook_path.lstrip('/')}"

    def _wait_for_page_registration(
        self,
        *,
        notion_page_id: str,
        expected_title: str,
        expected_dedup_key: str,
    ) -> None:
        def predicate(page: dict[str, object]) -> bool:
            properties = self._page_properties(page)
            return (
                self._title_property(properties, "Title") == expected_title
                and self._rich_text_property(properties, "DedupKey") == expected_dedup_key
                and self._status_property(properties, "Status") == "Registered"
            )

        self._wait_for_page_condition(
            notion_page_id=notion_page_id,
            description="registered inquiry values",
            predicate=predicate,
        )

    def _wait_for_page_completion(
        self,
        *,
        notion_page_id: str,
        expected_resolution: str,
    ) -> None:
        def predicate(page: dict[str, object]) -> bool:
            properties = self._page_properties(page)
            return (
                self._status_property(properties, "Status") == "Completed"
                and self._rich_text_property(properties, "Resolution") == expected_resolution
            )

        self._wait_for_page_condition(
            notion_page_id=notion_page_id,
            description="completed inquiry values",
            predicate=predicate,
        )

    def _wait_for_page_condition(
        self,
        *,
        notion_page_id: str,
        description: str,
        predicate: Callable[[dict[str, object]], bool],
    ) -> None:
        deadline = time.monotonic() + 20.0
        while True:
            page = self.notion_client.retrieve_page(notion_page_id)
            if predicate(page):
                return
            if time.monotonic() >= deadline:
                raise N8nIntegrationTestError(
                    f"Timed out waiting for Notion page {notion_page_id} to reflect {description}"
                )
            time.sleep(1.0)

    def _page_properties(self, page: dict[str, object]) -> dict[str, dict[str, object]]:
        properties = page.get("properties")
        if not isinstance(properties, dict):
            raise N8nIntegrationTestError("Notion page payload did not include properties")
        return {
            key: value
            for key, value in properties.items()
            if isinstance(key, str) and isinstance(value, dict)
        }

    def _title_property(self, properties: dict[str, dict[str, object]], name: str) -> str:
        prop = properties.get(name, {})
        return rich_text_to_plain_text(prop.get("title"))

    def _rich_text_property(self, properties: dict[str, dict[str, object]], name: str) -> str:
        prop = properties.get(name, {})
        return rich_text_to_plain_text(prop.get("rich_text"))

    def _status_property(self, properties: dict[str, dict[str, object]], name: str) -> str:
        prop = properties.get(name, {})
        status = prop.get("status")
        if not isinstance(status, dict):
            return ""
        value = status.get("name")
        return value if isinstance(value, str) else ""

    def _required_string(self, payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise N8nIntegrationTestError(f"Response is missing a non-empty string field: {key}")
        return value
