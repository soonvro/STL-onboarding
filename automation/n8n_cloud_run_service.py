from __future__ import annotations

import subprocess
from dataclasses import dataclass

from automation.envfile import N8nCloudRunConfig


class CommandExecutionError(RuntimeError):
    """Raised when an external command fails."""


@dataclass(slots=True)
class N8nCloudRunResult:
    service_name: str
    region: str
    base_url: str


class SubprocessRunner:
    def run(self, args: list[str]) -> str:
        completed = subprocess.run(args, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise CommandExecutionError(completed.stderr.strip() or completed.stdout.strip() or "command failed")
        return completed.stdout.strip()


class N8nCloudRunService:
    def __init__(self, config: N8nCloudRunConfig, runner: SubprocessRunner | None = None) -> None:
        self.config = config
        self.runner = runner or SubprocessRunner()

    def deploy(self) -> N8nCloudRunResult:
        self._enable_run_api()
        self._deploy_service()
        base_url = self._describe_base_url()
        self._update_service_urls(base_url)
        return N8nCloudRunResult(
            service_name=self.config.n8n_service_name,
            region=self.config.gcp_region,
            base_url=base_url,
        )

    def describe(self) -> N8nCloudRunResult:
        base_url = self._describe_base_url()
        return N8nCloudRunResult(
            service_name=self.config.n8n_service_name,
            region=self.config.gcp_region,
            base_url=base_url,
        )

    def _enable_run_api(self) -> None:
        self.runner.run(
            [
                "gcloud",
                "services",
                "enable",
                "run.googleapis.com",
                f"--project={self.config.gcp_project_id}",
            ]
        )

    def _deploy_service(self) -> None:
        self.runner.run(
            [
                "gcloud",
                "run",
                "deploy",
                self.config.n8n_service_name,
                f"--project={self.config.gcp_project_id}",
                f"--region={self.config.gcp_region}",
                f"--image={self.config.n8n_image}",
                "--allow-unauthenticated",
                "--port=5678",
                f"--memory={self.config.n8n_memory}",
                "--no-cpu-throttling",
                f"--scaling={self.config.n8n_scaling}",
                "--set-env-vars="
                + ",".join(
                    [
                        "N8N_ENDPOINT_HEALTH=health",
                        f"GENERIC_TIMEZONE={self.config.n8n_timezone}",
                        f"TZ={self.config.n8n_timezone}",
                        f"N8N_SHARED_SECRET={self.config.n8n_shared_secret}",
                    ]
                ),
            ]
        )

    def _describe_base_url(self) -> str:
        return self.runner.run(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                self.config.n8n_service_name,
                f"--project={self.config.gcp_project_id}",
                f"--region={self.config.gcp_region}",
                "--format=value(status.url)",
            ]
        )

    def _update_service_urls(self, base_url: str) -> None:
        self.runner.run(
            [
                "gcloud",
                "run",
                "services",
                "update",
                self.config.n8n_service_name,
                f"--project={self.config.gcp_project_id}",
                f"--region={self.config.gcp_region}",
                "--update-env-vars="
                + ",".join(
                    [
                        f"N8N_EDITOR_BASE_URL={base_url}",
                        f"WEBHOOK_URL={base_url}",
                    ]
                ),
            ]
        )
