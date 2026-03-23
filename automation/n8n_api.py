from __future__ import annotations

from dataclasses import dataclass, field

import httpx


class N8nApiError(RuntimeError):
    """Raised when the n8n API returns an error response."""


@dataclass(slots=True)
class N8nApiClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 30.0
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url.rstrip("/") + "/api/v1",
            timeout=self.timeout_seconds,
            headers={
                "X-N8N-API-KEY": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "N8nApiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def list_workflows(self) -> list[dict[str, object]]:
        payload = self._request("GET", "/workflows")
        return _extract_list(payload)

    def get_workflow(self, workflow_id: str) -> dict[str, object]:
        payload = self._request("GET", f"/workflows/{workflow_id}")
        return _extract_object(payload)

    def create_workflow(self, workflow: dict[str, object]) -> dict[str, object]:
        payload = self._request("POST", "/workflows", json=workflow)
        return _extract_object(payload)

    def update_workflow(self, workflow_id: str, workflow: dict[str, object]) -> dict[str, object]:
        payload = self._request("PUT", f"/workflows/{workflow_id}", json=workflow)
        return _extract_object(payload)

    def activate_workflow(self, workflow_id: str) -> dict[str, object]:
        payload = self._request("POST", f"/workflows/{workflow_id}/activate")
        return _extract_object(payload)

    def get_credential_schema(self, credential_type_name: str) -> dict[str, object]:
        payload = self._request("GET", f"/credentials/schema/{credential_type_name}")
        return _extract_object(payload)

    def create_credential(self, credential: dict[str, object]) -> dict[str, object]:
        payload = self._request("POST", "/credentials", json=credential)
        return _extract_object(payload)

    def update_credential(self, credential_id: str, credential: dict[str, object]) -> dict[str, object]:
        payload = self._request("PATCH", f"/credentials/{credential_id}", json=credential)
        return _extract_object(payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> dict[str, object] | list[object]:
        response = self._client.request(method, path, json=json)
        if response.is_success:
            return response.json()

        message = f"n8n API request failed with {response.status_code}"
        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        raise N8nApiError(f"{message}: {payload}")


def _extract_list(payload: dict[str, object] | list[object]) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise N8nApiError(f"Expected a list response, got: {payload!r}")


def _extract_object(payload: dict[str, object] | list[object]) -> dict[str, object]:
    if isinstance(payload, dict):
        for key in ("data", "item"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return payload
    raise N8nApiError(f"Expected an object response, got: {payload!r}")
