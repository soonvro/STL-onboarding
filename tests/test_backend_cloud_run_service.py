from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from automation.backend_cloud_run_service import BackendCloudRunService
from automation.envfile import BackendCloudRunConfig


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, args: list[str]) -> str:
        self.commands.append(args)
        if args[:4] == ["gcloud", "run", "services", "describe"]:
            return "https://qna-backend-xyz.a.run.app"
        return ""


class BackendCloudRunServiceTest(unittest.TestCase):
    def make_config(self) -> BackendCloudRunConfig:
        return BackendCloudRunConfig(
            gcp_project_id="demo-project",
            gcp_region="asia-northeast3",
            backend_service_name="qna-backend",
            backend_image="gcr.io/demo-project/qna-backend",
            backend_memory="1Gi",
            backend_vpc_network="default",
            backend_vpc_subnet="default",
            backend_vpc_egress="private-ranges-only",
        )

    def test_deploy_builds_and_deploys_backend_service(self) -> None:
        runner = FakeRunner()
        service = BackendCloudRunService(self.make_config(), runner=runner)
        env = {
            "ADMIN_PASSWORD": "secret",
            "ADMIN_JWT_SECRET": "jwt",
            "ADMIN_JWT_TTL_MINUTES": "60",
            "ADMIN_COOKIE_NAME": "admin_session",
            "ADMIN_COOKIE_SECURE": "true",
            "ADMIN_COOKIE_SAMESITE": "none",
            "BACKEND_ALLOWED_ORIGINS": "https://app.example.com",
            "BACKEND_CORS_ALLOW_CREDENTIALS": "true",
            "REDIS_URL": "redis://redis:6379/0",
            "NOTION_TOKEN": "notion",
            "NOTION_API_VERSION": "2026-03-11",
            "NOTION_DATABASE_ID": "database-id",
            "NOTION_DATA_SOURCE_ID": "data-source-id",
            "N8N_BASE_URL": "https://n8n.example.com",
            "N8N_SHARED_SECRET": "shared-secret",
            "N8N_WEBHOOK_REGISTER_PATH": "register",
            "N8N_WEBHOOK_COMPLETE_PATH": "complete",
            "ADMIN_NOTIFICATION_EMAIL": "admin@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            result = service.deploy()

        self.assertEqual(result.base_url, "https://qna-backend-xyz.a.run.app")
        self.assertEqual(runner.commands[0][:3], ["gcloud", "services", "enable"])
        self.assertEqual(runner.commands[1][:4], ["gcloud", "auth", "configure-docker", "gcr.io"])
        self.assertEqual(runner.commands[2][:3], ["docker", "build", "-f"])
        self.assertEqual(runner.commands[3][:2], ["docker", "push"])
        self.assertEqual(runner.commands[4][:3], ["gcloud", "run", "deploy"])
        self.assertIn("--network=default", runner.commands[4])
        self.assertIn("--subnet=default", runner.commands[4])
        self.assertIn("--vpc-egress=private-ranges-only", runner.commands[4])
        self.assertIn("--ingress=all", runner.commands[4])
        self.assertIn("--default-url", runner.commands[4])
