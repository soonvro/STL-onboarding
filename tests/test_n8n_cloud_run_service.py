from __future__ import annotations

import unittest

from automation.envfile import N8nCloudRunConfig
from automation.n8n_cloud_run_service import N8nCloudRunService


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, args: list[str]) -> str:
        self.commands.append(args)
        if args[:4] == ["gcloud", "run", "services", "describe"]:
            return "https://n8n-demo-xyz.a.run.app"
        return ""


class N8nCloudRunServiceTest(unittest.TestCase):
    def make_config(self) -> N8nCloudRunConfig:
        return N8nCloudRunConfig(
            gcp_project_id="demo-project",
            gcp_region="asia-northeast3",
            n8n_service_name="n8n-demo",
            n8n_image="n8nio/n8n:2.7.4",
            n8n_memory="2Gi",
            n8n_scaling="1",
            n8n_timezone="Asia/Seoul",
            n8n_shared_secret="shared-secret",
            n8n_base_url=None,
        )

    def test_deploy_enables_api_deploys_service_and_updates_urls(self) -> None:
        runner = FakeRunner()
        result = N8nCloudRunService(self.make_config(), runner=runner).deploy()

        self.assertEqual(result.base_url, "https://n8n-demo-xyz.a.run.app")
        self.assertEqual(len(runner.commands), 4)
        self.assertEqual(
            runner.commands[0],
            ["gcloud", "services", "enable", "run.googleapis.com", "--project=demo-project"],
        )
        self.assertIn("--image=n8nio/n8n:2.7.4", runner.commands[1])
        self.assertIn("--scaling=1", runner.commands[1])
        self.assertIn(
            "--set-env-vars=N8N_ENDPOINT_HEALTH=health,GENERIC_TIMEZONE=Asia/Seoul,TZ=Asia/Seoul,N8N_SHARED_SECRET=shared-secret",
            runner.commands[1],
        )
        self.assertIn("--update-env-vars=N8N_EDITOR_BASE_URL=https://n8n-demo-xyz.a.run.app,WEBHOOK_URL=https://n8n-demo-xyz.a.run.app", runner.commands[3])

    def test_describe_only_calls_describe(self) -> None:
        runner = FakeRunner()
        result = N8nCloudRunService(self.make_config(), runner=runner).describe()

        self.assertEqual(result.base_url, "https://n8n-demo-xyz.a.run.app")
        self.assertEqual(len(runner.commands), 1)
        self.assertEqual(runner.commands[0][:4], ["gcloud", "run", "services", "describe"])


if __name__ == "__main__":
    unittest.main()
