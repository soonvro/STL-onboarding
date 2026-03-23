from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from automation.envfile import BackendCloudRunConfig


class BackendCloudRunError(RuntimeError):
    """Raised when a Cloud Run deployment command fails."""


@dataclass(slots=True)
class BackendCloudRunResult:
    service_name: str
    region: str
    base_url: str
    image: str


class BackendSubprocessRunner:
    def run(self, args: list[str]) -> str:
        completed = subprocess.run(args, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise BackendCloudRunError(completed.stderr.strip() or completed.stdout.strip() or "command failed")
        return completed.stdout.strip()


@dataclass(slots=True)
class BackendCloudRunService:
    config: BackendCloudRunConfig
    runner: BackendSubprocessRunner | None = None

    def __post_init__(self) -> None:
        if self.runner is None:
            self.runner = BackendSubprocessRunner()

    def deploy(self) -> BackendCloudRunResult:
        assert self.runner is not None
        self.runner.run(["gcloud", "services", "enable", "run.googleapis.com", f"--project={self.config.gcp_project_id}"])
        registry_host = _registry_host_for_image(self.config.backend_image)
        if _requires_gcloud_docker_auth(registry_host):
            self.runner.run(["gcloud", "auth", "configure-docker", registry_host, "--quiet"])
        self.runner.run(["docker", "build", "-f", "backend/Dockerfile", "-t", self.config.backend_image, "."])
        self.runner.run(["docker", "push", self.config.backend_image])
        with self._runtime_env_file() as env_file:
            self.runner.run(
                [
                    "gcloud",
                    "run",
                    "deploy",
                    self.config.backend_service_name,
                    f"--project={self.config.gcp_project_id}",
                    f"--region={self.config.gcp_region}",
                    f"--image={self.config.backend_image}",
                    f"--memory={self.config.backend_memory}",
                    f"--network={self.config.backend_vpc_network}",
                    f"--subnet={self.config.backend_vpc_subnet}",
                    f"--vpc-egress={self.config.backend_vpc_egress}",
                    "--ingress=all",
                    "--default-url",
                    "--allow-unauthenticated",
                    f"--env-vars-file={env_file}",
                ]
            )
        base_url = self.describe().base_url
        return BackendCloudRunResult(
            service_name=self.config.backend_service_name,
            region=self.config.gcp_region,
            base_url=base_url,
            image=self.config.backend_image,
        )

    def describe(self) -> BackendCloudRunResult:
        assert self.runner is not None
        base_url = self.runner.run(
            [
                "gcloud",
                "run",
                "services",
                "describe",
                self.config.backend_service_name,
                f"--project={self.config.gcp_project_id}",
                f"--region={self.config.gcp_region}",
                "--format=value(status.url)",
            ]
        )
        return BackendCloudRunResult(
            service_name=self.config.backend_service_name,
            region=self.config.gcp_region,
            base_url=base_url,
            image=self.config.backend_image,
        )

    def _runtime_env_file(self) -> tempfile.NamedTemporaryFile[str]:
        required_env_names = [
            "ADMIN_PASSWORD",
            "ADMIN_JWT_SECRET",
            "ADMIN_JWT_TTL_MINUTES",
            "ADMIN_COOKIE_NAME",
            "ADMIN_COOKIE_SECURE",
            "ADMIN_COOKIE_SAMESITE",
            "BACKEND_ALLOWED_ORIGINS",
            "BACKEND_CORS_ALLOW_CREDENTIALS",
            "REDIS_URL",
            "NOTION_TOKEN",
            "NOTION_API_VERSION",
            "NOTION_DATABASE_ID",
            "NOTION_DATA_SOURCE_ID",
            "N8N_BASE_URL",
            "N8N_SHARED_SECRET",
            "N8N_WEBHOOK_REGISTER_PATH",
            "N8N_WEBHOOK_COMPLETE_PATH",
            "ADMIN_NOTIFICATION_EMAIL",
        ]
        missing = [name for name in required_env_names if not os.environ.get(name)]
        if missing:
            raise BackendCloudRunError("Missing required backend runtime env vars: " + ", ".join(missing))

        temp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml")
        for name in required_env_names:
            value = os.environ[name]
            temp.write(f"{name}: {value!r}\n")
        temp.flush()
        temp.close()
        return _NamedTempFileContext(Path(temp.name))


@dataclass(slots=True)
class _NamedTempFileContext:
    path: Path

    def __enter__(self) -> str:
        return str(self.path)

    def __exit__(self, *_: object) -> None:
        self.path.unlink(missing_ok=True)


def _registry_host_for_image(image: str) -> str:
    first_segment = image.split("/", 1)[0]
    if "." in first_segment or ":" in first_segment or first_segment == "localhost":
        return first_segment
    return "docker.io"


def _requires_gcloud_docker_auth(registry_host: str) -> bool:
    return registry_host.endswith(".gcr.io") or registry_host == "gcr.io" or registry_host.endswith(".pkg.dev")
