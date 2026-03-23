from __future__ import annotations

import copy
import unittest

from automation.envfile import N8nBootstrapConfig
from automation.n8n_bootstrap_service import (
    COMPLETE_WORKFLOW_NAME,
    N8nBootstrapError,
    N8nBootstrapService,
    REGISTER_WORKFLOW_NAME,
)


def make_workflow_payload(name: str, *, active: bool, webhook_path: str, from_email: str) -> dict[str, object]:
    if name == REGISTER_WORKFLOW_NAME:
        return {
            "id": "wf-register",
            "name": name,
            "active": active,
            "nodes": [
                {"name": "Webhook", "parameters": {"path": webhook_path}},
                {"name": "Create Notion Page", "credentials": {"notionApi": {"id": "cred-notion", "name": "QnA Notion"}}},
                {"name": "Send Admin Email", "parameters": {"fromEmail": from_email}, "credentials": {"smtp": {"id": "cred-smtp", "name": "QnA SMTP"}}},
            ],
        }
    return {
        "id": "wf-complete",
        "name": name,
        "active": active,
        "nodes": [
            {"name": "Webhook", "parameters": {"path": webhook_path}},
            {"name": "Update Notion Page", "credentials": {"notionApi": {"id": "cred-notion", "name": "QnA Notion"}}},
            {"name": "Send Requester Result Email", "parameters": {"fromEmail": from_email}, "credentials": {"smtp": {"id": "cred-smtp", "name": "QnA SMTP"}}},
            {"name": "Send Admin Completion Email", "parameters": {"fromEmail": from_email}, "credentials": {"smtp": {"id": "cred-smtp", "name": "QnA SMTP"}}},
        ],
    }


class FakeN8nApiClient:
    def __init__(self) -> None:
        self.schemas = {
            "notionApi": {"properties": {"apiKey": {"type": "string"}}},
            "smtp": {"properties": {"host": {}, "port": {}, "user": {}, "password": {}, "secure": {}}},
        }
        self.credentials: dict[str, dict[str, object]] = {}
        self.workflows: dict[str, dict[str, object]] = {}
        self.created_credential_payloads: list[dict[str, object]] = []
        self.created_workflow_payloads: list[dict[str, object]] = []
        self.updated_workflow_payloads: list[tuple[str, dict[str, object]]] = []

    def list_credentials(self) -> list[dict[str, object]]:
        return list(self.credentials.values())

    def get_credential_schema(self, credential_type_name: str) -> dict[str, object]:
        return self.schemas[credential_type_name]

    def create_credential(self, credential: dict[str, object]) -> dict[str, object]:
        self.created_credential_payloads.append(copy.deepcopy(credential))
        credential_id = "cred-notion" if credential["type"] == "notionApi" else "cred-smtp"
        payload = {"id": credential_id, **credential}
        self.credentials[credential_id] = payload
        return payload

    def update_credential(self, credential_id: str, credential: dict[str, object]) -> dict[str, object]:
        payload = {"id": credential_id, **credential}
        self.credentials[credential_id] = payload
        return payload

    def list_workflows(self) -> list[dict[str, object]]:
        return [{"id": workflow["id"], "name": workflow["name"], "active": workflow.get("active", False)} for workflow in self.workflows.values()]

    def create_workflow(self, workflow: dict[str, object]) -> dict[str, object]:
        self.created_workflow_payloads.append(copy.deepcopy(workflow))
        workflow_id = "wf-register" if workflow["name"] == REGISTER_WORKFLOW_NAME else "wf-complete"
        payload = {"id": workflow_id, "active": False, **copy.deepcopy(workflow)}
        self.workflows[workflow_id] = payload
        return payload

    def update_workflow(self, workflow_id: str, workflow: dict[str, object]) -> dict[str, object]:
        self.updated_workflow_payloads.append((workflow_id, copy.deepcopy(workflow)))
        payload = {"id": workflow_id, "active": self.workflows[workflow_id].get("active", False), **copy.deepcopy(workflow)}
        self.workflows[workflow_id] = payload
        return payload

    def activate_workflow(self, workflow_id: str) -> dict[str, object]:
        self.workflows[workflow_id]["active"] = True
        return copy.deepcopy(self.workflows[workflow_id])

    def get_workflow(self, workflow_id: str) -> dict[str, object]:
        return copy.deepcopy(self.workflows[workflow_id])


class N8nBootstrapServiceTest(unittest.TestCase):
    def make_config(self) -> N8nBootstrapConfig:
        return N8nBootstrapConfig(
            n8n_base_url="https://n8n-demo.example.com",
            n8n_api_key="api-key",
            n8n_shared_secret="shared-secret",
            n8n_webhook_register_path="qna-register-prod",
            n8n_webhook_complete_path="qna-complete-prod",
            n8n_from_email="Q&A Bot <bot@example.com>",
            n8n_notion_credential_name="QnA Notion",
            n8n_smtp_credential_name="QnA SMTP",
            n8n_notion_credential_id=None,
            n8n_smtp_credential_id=None,
            notion_token="notion-secret",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="smtp-user",
            smtp_password="smtp-pass",
            smtp_secure=True,
        )

    def test_sync_creates_credentials_and_workflows_with_runtime_patches(self) -> None:
        client = FakeN8nApiClient()
        result = N8nBootstrapService(self.make_config(), client).sync()

        self.assertEqual(result.notion_credential_id, "cred-notion")
        self.assertEqual(result.smtp_credential_id, "cred-smtp")
        self.assertEqual(result.register_workflow_id, "wf-register")
        self.assertEqual(result.complete_workflow_id, "wf-complete")
        self.assertEqual(len(client.created_credential_payloads), 2)
        self.assertEqual(len(client.created_workflow_payloads), 2)

        register_payload = client.created_workflow_payloads[0]
        register_nodes = {node["name"]: node for node in register_payload["nodes"]}
        self.assertEqual(register_nodes["Webhook"]["parameters"]["path"], "qna-register-prod")
        self.assertEqual(register_nodes["Send Admin Email"]["parameters"]["fromEmail"], "Q&A Bot <bot@example.com>")
        self.assertEqual(register_nodes["Create Notion Page"]["credentials"]["notionApi"]["id"], "cred-notion")
        self.assertEqual(register_nodes["Send Admin Email"]["credentials"]["smtp"]["id"], "cred-smtp")
        self.assertIn("shared-secret", register_nodes["Validate Shared Secret and Input"]["parameters"]["jsCode"])
        self.assertNotIn(
            "__N8N_SHARED_SECRET__",
            register_nodes["Validate Shared Secret and Input"]["parameters"]["jsCode"],
        )

    def test_verify_requires_active_workflows_with_patched_runtime_values(self) -> None:
        client = FakeN8nApiClient()
        client.credentials = {
            "cred-notion": {"id": "cred-notion", "name": "QnA Notion", "type": "notionApi"},
            "cred-smtp": {"id": "cred-smtp", "name": "QnA SMTP", "type": "smtp"},
        }
        client.workflows = {
            "wf-register": make_workflow_payload(
                REGISTER_WORKFLOW_NAME,
                active=True,
                webhook_path="qna-register-prod",
                from_email="Q&A Bot <bot@example.com>",
            ),
            "wf-complete": make_workflow_payload(
                COMPLETE_WORKFLOW_NAME,
                active=True,
                webhook_path="qna-complete-prod",
                from_email="Q&A Bot <bot@example.com>",
            ),
        }

        result = N8nBootstrapService(self.make_config(), client).verify()

        self.assertEqual(result.register_workflow_id, "wf-register")
        self.assertEqual(result.complete_workflow_id, "wf-complete")

    def test_verify_fails_when_placeholder_email_remains(self) -> None:
        client = FakeN8nApiClient()
        client.credentials = {
            "cred-notion": {"id": "cred-notion", "name": "QnA Notion", "type": "notionApi"},
            "cred-smtp": {"id": "cred-smtp", "name": "QnA SMTP", "type": "smtp"},
        }
        client.workflows = {
            "wf-register": make_workflow_payload(
                REGISTER_WORKFLOW_NAME,
                active=True,
                webhook_path="qna-register-prod",
                from_email="Q&A Bot <change-me@example.com>",
            ),
            "wf-complete": make_workflow_payload(
                COMPLETE_WORKFLOW_NAME,
                active=True,
                webhook_path="qna-complete-prod",
                from_email="Q&A Bot <bot@example.com>",
            ),
        }

        with self.assertRaises(N8nBootstrapError) as context:
            N8nBootstrapService(self.make_config(), client).verify()

        self.assertIn("placeholder", str(context.exception))


if __name__ == "__main__":
    unittest.main()
