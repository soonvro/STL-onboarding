from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

from automation.envfile import N8nBootstrapConfig
from automation.n8n_api import N8nApiClient


REGISTER_WORKFLOW_NAME = "001 문의 등록"
COMPLETE_WORKFLOW_NAME = "002 문의 완료"
REGISTER_WORKFLOW_PATH = Path("n8n/workflows/001_문의_등록.json")
COMPLETE_WORKFLOW_PATH = Path("n8n/workflows/002_문의_완료.json")


class N8nBootstrapError(RuntimeError):
    """Raised when the bootstrap process cannot complete safely."""


@dataclass(slots=True)
class CredentialBinding:
    credential_id: str
    name: str
    credential_type: str


@dataclass(slots=True)
class WorkflowBinding:
    workflow_id: str
    name: str
    active: bool


@dataclass(slots=True)
class N8nBootstrapResult:
    base_url: str
    notion_credential_id: str
    smtp_credential_id: str
    register_workflow_id: str
    complete_workflow_id: str


class N8nBootstrapService:
    def __init__(self, config: N8nBootstrapConfig, client: N8nApiClient) -> None:
        self.config = config
        self.client = client

    def sync(self) -> N8nBootstrapResult:
        discovered_credentials = self._discover_credentials_from_existing_workflows()
        notion_credential = self._upsert_credential(
            name=self.config.n8n_notion_credential_name,
            credential_type="notionApi",
            data=self._build_notion_credential_data(),
            existing_credential_id=self.config.n8n_notion_credential_id
            or discovered_credentials.get("notionApi"),
        )
        smtp_credential = self._upsert_credential(
            name=self.config.n8n_smtp_credential_name,
            credential_type="smtp",
            data=self._build_smtp_credential_data(),
            existing_credential_id=self.config.n8n_smtp_credential_id
            or discovered_credentials.get("smtp"),
        )

        register_workflow = self._upsert_workflow(
            workflow_path=REGISTER_WORKFLOW_PATH,
            workflow_name=REGISTER_WORKFLOW_NAME,
            webhook_path=self.config.n8n_webhook_register_path,
            notion_credential=notion_credential,
            smtp_credential=smtp_credential,
        )
        complete_workflow = self._upsert_workflow(
            workflow_path=COMPLETE_WORKFLOW_PATH,
            workflow_name=COMPLETE_WORKFLOW_NAME,
            webhook_path=self.config.n8n_webhook_complete_path,
            notion_credential=notion_credential,
            smtp_credential=smtp_credential,
        )

        return N8nBootstrapResult(
            base_url=self.config.n8n_base_url,
            notion_credential_id=notion_credential.credential_id,
            smtp_credential_id=smtp_credential.credential_id,
            register_workflow_id=register_workflow.workflow_id,
            complete_workflow_id=complete_workflow.workflow_id,
        )

    def verify(self) -> N8nBootstrapResult:
        register_workflow = self._require_workflow(REGISTER_WORKFLOW_NAME)
        complete_workflow = self._require_workflow(COMPLETE_WORKFLOW_NAME)
        register_payload = self.client.get_workflow(register_workflow.workflow_id)
        complete_payload = self.client.get_workflow(complete_workflow.workflow_id)

        notion_credential = self._require_credential_binding(
            credential_type="notionApi",
            configured_id=self.config.n8n_notion_credential_id,
            workflow_payloads=[register_payload, complete_payload],
            fallback_name=self.config.n8n_notion_credential_name,
        )
        smtp_credential = self._require_credential_binding(
            credential_type="smtp",
            configured_id=self.config.n8n_smtp_credential_id,
            workflow_payloads=[register_payload, complete_payload],
            fallback_name=self.config.n8n_smtp_credential_name,
        )

        self._verify_workflow_shape(register_workflow, self.config.n8n_webhook_register_path)
        self._verify_workflow_shape(complete_workflow, self.config.n8n_webhook_complete_path)

        return N8nBootstrapResult(
            base_url=self.config.n8n_base_url,
            notion_credential_id=notion_credential.credential_id,
            smtp_credential_id=smtp_credential.credential_id,
            register_workflow_id=register_workflow.workflow_id,
            complete_workflow_id=complete_workflow.workflow_id,
        )

    def _build_notion_credential_data(self) -> dict[str, object]:
        schema = self.client.get_credential_schema("notionApi")
        schema_fields = _schema_field_names(schema)
        token_field = _first_present(schema_fields, ["apiKey", "internalIntegrationSecret", "token"])
        return {token_field: self.config.notion_token}

    def _build_smtp_credential_data(self) -> dict[str, object]:
        schema = self.client.get_credential_schema("smtp")
        schema_fields = _schema_field_names(schema)

        data: dict[str, object] = {}
        host_field = _first_present(schema_fields, ["host", "hostName"])
        secure_field = _first_present(schema_fields, ["secure", "ssl"])

        data[host_field] = self.config.smtp_host
        data["port"] = self.config.smtp_port
        data["user"] = self.config.smtp_user
        data["password"] = self.config.smtp_password
        data[secure_field] = self.config.smtp_secure

        return data

    def _upsert_credential(
        self,
        *,
        name: str,
        credential_type: str,
        data: dict[str, object],
        existing_credential_id: str | None,
    ) -> CredentialBinding:
        payload = {
            "name": name,
            "type": credential_type,
            "data": data,
        }
        if existing_credential_id:
            updated = self.client.update_credential(existing_credential_id, payload)
            return self._credential_binding_from_payload(updated, credential_type=credential_type, fallback_name=name)

        created = self.client.create_credential(payload)
        return self._credential_binding_from_payload(created, credential_type=credential_type, fallback_name=name)

    def _credential_binding_from_payload(
        self,
        payload: dict[str, object],
        *,
        credential_type: str,
        fallback_name: str,
    ) -> CredentialBinding:
        credential_id = payload.get("id")
        if not isinstance(credential_id, str):
            raise N8nBootstrapError(f"Credential response did not include an id for {fallback_name}")

        name = payload.get("name")
        if not isinstance(name, str):
            name = fallback_name

        return CredentialBinding(credential_id=credential_id, name=name, credential_type=credential_type)

    def _upsert_workflow(
        self,
        *,
        workflow_path: Path,
        workflow_name: str,
        webhook_path: str,
        notion_credential: CredentialBinding,
        smtp_credential: CredentialBinding,
    ) -> WorkflowBinding:
        existing = self._find_workflow_by_name(workflow_name)
        payload = self._materialize_workflow(
            workflow_path=workflow_path,
            webhook_path=webhook_path,
            notion_credential=notion_credential,
            smtp_credential=smtp_credential,
        )

        if existing:
            updated = self.client.update_workflow(existing.workflow_id, payload)
            workflow = self._workflow_binding_from_payload(updated, fallback_name=workflow_name)
        else:
            created = self.client.create_workflow(payload)
            workflow = self._workflow_binding_from_payload(created, fallback_name=workflow_name)

        self.client.activate_workflow(workflow.workflow_id)
        verified = self._require_workflow(workflow_name)
        return verified

    def _require_workflow(self, workflow_name: str) -> WorkflowBinding:
        workflow = self._find_workflow_by_name(workflow_name)
        if workflow is None:
            raise N8nBootstrapError(f"Workflow not found: {workflow_name}")
        full_workflow = self.client.get_workflow(workflow.workflow_id)
        binding = self._workflow_binding_from_payload(full_workflow, fallback_name=workflow_name)
        if not binding.active:
            raise N8nBootstrapError(f"Workflow is not active: {workflow_name}")
        return binding

    def _find_workflow_by_name(self, workflow_name: str) -> WorkflowBinding | None:
        for item in self.client.list_workflows():
            name = item.get("name")
            workflow_id = item.get("id")
            active = bool(item.get("active"))
            if name == workflow_name and isinstance(workflow_id, str):
                return WorkflowBinding(workflow_id=workflow_id, name=workflow_name, active=active)
        return None

    def _workflow_binding_from_payload(self, payload: dict[str, object], *, fallback_name: str) -> WorkflowBinding:
        workflow_id = payload.get("id")
        if not isinstance(workflow_id, str):
            raise N8nBootstrapError(f"Workflow response did not include an id for {fallback_name}")

        name = payload.get("name")
        if not isinstance(name, str):
            name = fallback_name

        return WorkflowBinding(
            workflow_id=workflow_id,
            name=name,
            active=bool(payload.get("active")),
        )

    def _discover_credentials_from_existing_workflows(self) -> dict[str, str]:
        discovered: dict[str, str] = {}

        for workflow_name in (REGISTER_WORKFLOW_NAME, COMPLETE_WORKFLOW_NAME):
            binding = self._find_workflow_by_name(workflow_name)
            if binding is None:
                continue
            payload = self.client.get_workflow(binding.workflow_id)
            for credential_type in ("notionApi", "smtp"):
                credential = self._extract_credential_binding_from_workflow(
                    payload,
                    credential_type=credential_type,
                    fallback_name=(
                        self.config.n8n_notion_credential_name
                        if credential_type == "notionApi"
                        else self.config.n8n_smtp_credential_name
                    ),
                )
                if credential is not None:
                    discovered[credential_type] = credential.credential_id

        return discovered

    def _require_credential_binding(
        self,
        *,
        credential_type: str,
        configured_id: str | None,
        workflow_payloads: list[dict[str, object]],
        fallback_name: str,
    ) -> CredentialBinding:
        if configured_id:
            return CredentialBinding(
                credential_id=configured_id,
                name=fallback_name,
                credential_type=credential_type,
            )

        for workflow_payload in workflow_payloads:
            binding = self._extract_credential_binding_from_workflow(
                workflow_payload,
                credential_type=credential_type,
                fallback_name=fallback_name,
            )
            if binding is not None:
                return binding

        raise N8nBootstrapError(f"Credential binding not found for type: {credential_type}")

    def _extract_credential_binding_from_workflow(
        self,
        workflow_payload: dict[str, object],
        *,
        credential_type: str,
        fallback_name: str,
    ) -> CredentialBinding | None:
        nodes = workflow_payload.get("nodes")
        if not isinstance(nodes, list):
            return None

        for node in nodes:
            if not isinstance(node, dict):
                continue
            credentials = node.get("credentials")
            if not isinstance(credentials, dict):
                continue
            credential = credentials.get(credential_type)
            if not isinstance(credential, dict):
                continue
            credential_id = credential.get("id")
            if not isinstance(credential_id, str):
                continue
            name = credential.get("name")
            return CredentialBinding(
                credential_id=credential_id,
                name=name if isinstance(name, str) else fallback_name,
                credential_type=credential_type,
            )

        return None

    def _materialize_workflow(
        self,
        *,
        workflow_path: Path,
        webhook_path: str,
        notion_credential: CredentialBinding,
        smtp_credential: CredentialBinding,
    ) -> dict[str, object]:
        export = _load_workflow_export(workflow_path)
        workflow = copy.deepcopy(export)

        for node in workflow["nodes"]:
            name = node["name"]
            if name == "Webhook":
                node["parameters"]["path"] = webhook_path
                continue

            if name == "Validate Shared Secret and Input":
                js_code = node["parameters"].get("jsCode")
                if isinstance(js_code, str):
                    node["parameters"]["jsCode"] = js_code.replace(
                        "__N8N_SHARED_SECRET__",
                        _escape_js_single_quoted_string(self.config.n8n_shared_secret),
                    )
                continue

            if name in {"Create Notion Page", "Update Notion Page"}:
                node["credentials"] = {
                    notion_credential.credential_type: {
                        "id": notion_credential.credential_id,
                        "name": notion_credential.name,
                    }
                }
                continue

            if name in {"Send Admin Email", "Send Requester Result Email", "Send Admin Completion Email"}:
                node["parameters"]["fromEmail"] = self.config.n8n_from_email
                node["credentials"] = {
                    smtp_credential.credential_type: {
                        "id": smtp_credential.credential_id,
                        "name": smtp_credential.name,
                    }
                }

        return {
            "name": workflow["name"],
            "nodes": workflow["nodes"],
            "connections": workflow["connections"],
            "settings": workflow.get("settings", {}),
        }

    def _verify_workflow_shape(self, workflow: WorkflowBinding, expected_webhook_path: str) -> None:
        payload = self.client.get_workflow(workflow.workflow_id)
        nodes = payload.get("nodes")
        if not isinstance(nodes, list):
            raise N8nBootstrapError(f"Workflow nodes were missing for {workflow.name}")

        node_index: dict[str, dict[str, object]] = {}
        for node in nodes:
            if isinstance(node, dict):
                name = node.get("name")
                if isinstance(name, str):
                    node_index[name] = node

        webhook = node_index.get("Webhook")
        if webhook is None:
            raise N8nBootstrapError(f"Workflow {workflow.name} is missing the Webhook node")
        webhook_params = webhook.get("parameters")
        if not isinstance(webhook_params, dict) or webhook_params.get("path") != expected_webhook_path:
            raise N8nBootstrapError(f"Workflow {workflow.name} has an unexpected webhook path")

        for node_name in ("Send Admin Email", "Send Requester Result Email", "Send Admin Completion Email"):
            node = node_index.get(node_name)
            if node is None:
                continue
            parameters = node.get("parameters")
            if not isinstance(parameters, dict):
                raise N8nBootstrapError(f"Workflow {workflow.name} has invalid parameters for {node_name}")
            from_email = parameters.get("fromEmail")
            if not isinstance(from_email, str) or "change-me" in from_email:
                raise N8nBootstrapError(f"Workflow {workflow.name} still has a placeholder fromEmail in {node_name}")
            email_format = parameters.get("emailFormat")
            if email_format != "both":
                raise N8nBootstrapError(f"Workflow {workflow.name} must use emailFormat=both in {node_name}")
            for field_name in ("subject", "text", "html"):
                value = parameters.get(field_name)
                if not isinstance(value, str) or not value.strip():
                    raise N8nBootstrapError(
                        f"Workflow {workflow.name} is missing {field_name} template content in {node_name}"
                    )
            credentials = node.get("credentials")
            if not isinstance(credentials, dict) or "smtp" not in credentials:
                raise N8nBootstrapError(f"Workflow {workflow.name} is missing SMTP credentials on {node_name}")

        for node_name in ("Create Notion Page", "Update Notion Page"):
            node = node_index.get(node_name)
            if node is None:
                continue
            credentials = node.get("credentials")
            if not isinstance(credentials, dict) or "notionApi" not in credentials:
                raise N8nBootstrapError(f"Workflow {workflow.name} is missing Notion credentials on {node_name}")


def _load_workflow_export(workflow_path: Path) -> dict[str, object]:
    absolute_path = Path.cwd() / workflow_path
    try:
        data = json.loads(absolute_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise N8nBootstrapError(f"Workflow export not found: {workflow_path}") from exc
    except json.JSONDecodeError as exc:
        raise N8nBootstrapError(f"Workflow export is not valid JSON: {workflow_path}") from exc

    if not isinstance(data, dict):
        raise N8nBootstrapError(f"Workflow export root must be an object: {workflow_path}")
    if not isinstance(data.get("nodes"), list) or not isinstance(data.get("connections"), dict):
        raise N8nBootstrapError(f"Workflow export must contain nodes and connections: {workflow_path}")
    return data


def _escape_js_single_quoted_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _schema_field_names(schema: dict[str, object]) -> set[str]:
    field_names: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            properties = value.get("properties")
            if isinstance(properties, dict):
                field_names.update(key for key in properties if isinstance(key, str))
                for nested in properties.values():
                    walk(nested)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(schema)
    return field_names


def _first_present(options: set[str], candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in options:
            return candidate
    raise N8nBootstrapError(f"Could not find a matching field in schema for candidates: {', '.join(candidates)}")
