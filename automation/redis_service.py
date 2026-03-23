from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass

from automation.envfile import RedisAutomationConfig


class RedisAutomationError(RuntimeError):
    """Raised when a Redis infrastructure command fails."""


@dataclass(slots=True)
class RedisInstanceResult:
    instance_name: str
    region: str
    host: str
    port: int
    state: str

    @property
    def redis_url(self) -> str:
        return f"redis://{self.host}:{self.port}/0"


class RedisSubprocessRunner:
    def run(self, args: list[str]) -> str:
        completed = subprocess.run(args, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise RedisAutomationError(completed.stderr.strip() or completed.stdout.strip() or "command failed")
        return completed.stdout.strip()


@dataclass(slots=True)
class RedisAutomationService:
    config: RedisAutomationConfig
    runner: RedisSubprocessRunner | None = None

    def __post_init__(self) -> None:
        if self.runner is None:
            self.runner = RedisSubprocessRunner()

    def create(self) -> RedisInstanceResult:
        assert self.runner is not None
        self.runner.run(["gcloud", "services", "enable", "redis.googleapis.com", f"--project={self.config.gcp_project_id}"])
        try:
            existing = self.describe()
        except RedisAutomationError:
            existing = None

        if existing is None:
            self.runner.run(
                [
                    "gcloud",
                    "redis",
                    "instances",
                    "create",
                    self.config.redis_instance_name,
                    f"--project={self.config.gcp_project_id}",
                    f"--region={self.config.redis_region}",
                    f"--size={self.config.redis_size_gb}",
                    "--tier=basic",
                    f"--network={self.config.redis_network}",
                    "--connect-mode=DIRECT_PEERING",
                    f"--redis-version={self.config.redis_version}",
                ]
            )

        return self._wait_until_ready()

    def describe(self) -> RedisInstanceResult:
        assert self.runner is not None
        raw = self.runner.run(
            [
                "gcloud",
                "redis",
                "instances",
                "describe",
                self.config.redis_instance_name,
                f"--project={self.config.gcp_project_id}",
                f"--region={self.config.redis_region}",
                "--format=json",
            ]
        )
        return _parse_instance(raw)

    def destroy(self) -> None:
        assert self.runner is not None
        self.runner.run(
            [
                "gcloud",
                "redis",
                "instances",
                "delete",
                self.config.redis_instance_name,
                f"--project={self.config.gcp_project_id}",
                f"--region={self.config.redis_region}",
                "--quiet",
            ]
        )

    def _wait_until_ready(self, *, timeout_seconds: int = 900, interval_seconds: int = 5) -> RedisInstanceResult:
        deadline = time.monotonic() + timeout_seconds
        while True:
            instance = self.describe()
            if instance.state == "READY":
                return instance
            if time.monotonic() >= deadline:
                raise RedisAutomationError(
                    f"Timed out waiting for Redis instance {self.config.redis_instance_name} to become READY"
                )
            time.sleep(interval_seconds)


def _parse_instance(raw: str) -> RedisInstanceResult:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RedisAutomationError("Redis describe response was not valid JSON") from exc

    instance_name = payload.get("name")
    host = payload.get("host")
    port = payload.get("port")
    state = payload.get("state")
    region = payload.get("region")
    if not isinstance(region, str) or not region:
        if isinstance(instance_name, str) and "/locations/" in instance_name:
            region = instance_name.split("/locations/", 1)[1].split("/", 1)[0]

    if not isinstance(instance_name, str) or not instance_name:
        raise RedisAutomationError("Redis describe response did not include name")
    if not isinstance(host, str) or not host:
        raise RedisAutomationError("Redis describe response did not include host")
    if not isinstance(port, int):
        raise RedisAutomationError("Redis describe response did not include port")
    if not isinstance(state, str) or not state:
        raise RedisAutomationError("Redis describe response did not include state")
    if not isinstance(region, str) or not region:
        raise RedisAutomationError("Redis describe response did not include region")

    return RedisInstanceResult(
        instance_name=instance_name.rsplit("/", 1)[-1],
        region=region.rsplit("/", 1)[-1],
        host=host,
        port=port,
        state=state,
    )
