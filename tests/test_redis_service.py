from __future__ import annotations

import unittest

from automation.envfile import RedisAutomationConfig
from automation.redis_service import RedisAutomationError, RedisAutomationService


class FakeRedisRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self._created = False

    def run(self, args: list[str]) -> str:
        self.commands.append(args)
        if args[:4] == ["gcloud", "services", "enable", "redis.googleapis.com"]:
            return ""
        if args[:4] == ["gcloud", "redis", "instances", "describe"]:
            if not self._created:
                self._created = True
                raise RedisAutomationError("not found")
            return """
            {
              "name": "projects/demo-project/locations/asia-northeast3/instances/qna-redis",
              "region": "projects/demo-project/locations/asia-northeast3",
              "host": "10.0.0.5",
              "port": 6379,
              "state": "READY"
            }
            """
        if args[:4] == ["gcloud", "redis", "instances", "create"]:
            return ""
        if args[:4] == ["gcloud", "redis", "instances", "delete"]:
            return ""
        raise AssertionError(f"Unexpected command: {args}")


class RedisAutomationServiceTest(unittest.TestCase):
    def make_config(self) -> RedisAutomationConfig:
        return RedisAutomationConfig(
            gcp_project_id="demo-project",
            redis_instance_name="qna-redis",
            redis_region="asia-northeast3",
            redis_size_gb=1,
            redis_network="default",
            redis_version="redis_7_0",
        )

    def test_create_enables_api_and_returns_redis_url(self) -> None:
        runner = FakeRedisRunner()
        service = RedisAutomationService(self.make_config(), runner=runner)

        result = service.create()

        self.assertEqual(result.instance_name, "qna-redis")
        self.assertEqual(result.region, "asia-northeast3")
        self.assertEqual(result.host, "10.0.0.5")
        self.assertEqual(result.port, 6379)
        self.assertEqual(result.state, "READY")
        self.assertEqual(result.redis_url, "redis://10.0.0.5:6379/0")
        self.assertEqual(runner.commands[0][:4], ["gcloud", "services", "enable", "redis.googleapis.com"])
        self.assertEqual(runner.commands[1][:4], ["gcloud", "redis", "instances", "describe"])
        self.assertEqual(runner.commands[2][:4], ["gcloud", "redis", "instances", "create"])
        self.assertIn("--tier=basic", runner.commands[2])
        self.assertIn("--connect-mode=DIRECT_PEERING", runner.commands[2])
        self.assertIn("--network=default", runner.commands[2])
        self.assertIn("--redis-version=redis_7_0", runner.commands[2])

    def test_destroy_deletes_instance(self) -> None:
        runner = FakeRedisRunner()
        service = RedisAutomationService(self.make_config(), runner=runner)

        service.destroy()

        self.assertEqual(runner.commands[0][:4], ["gcloud", "redis", "instances", "delete"])
        self.assertIn("--quiet", runner.commands[0])
