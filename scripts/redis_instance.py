from __future__ import annotations

import argparse
import json
import sys

from automation.envfile import ConfigError, RedisAutomationConfig, load_dotenv_defaults
from automation.redis_service import RedisAutomationError, RedisAutomationService, RedisInstanceResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create, inspect, or destroy the Memorystore Redis instance.")
    parser.add_argument("--action", choices=("create", "describe", "destroy"), required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--format", choices=("env", "json"), default="env")
    return parser.parse_args()


def emit_result(result: RedisInstanceResult, *, output_format: str) -> None:
    if output_format == "json":
        json.dump(
            {
                "instance_name": result.instance_name,
                "region": result.region,
                "host": result.host,
                "port": result.port,
                "state": result.state,
                "redis_url": result.redis_url,
            },
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    print(f"REDIS_INSTANCE_NAME={result.instance_name}")
    print(f"REDIS_HOST={result.host}")
    print(f"REDIS_PORT={result.port}")
    print(f"REDIS_STATE={result.state}")
    print(f"REDIS_URL={result.redis_url}")


def main() -> int:
    args = parse_args()
    try:
        load_dotenv_defaults(args.env_file)
        config = RedisAutomationConfig.from_environment()
        config.validate_for_action(args.action)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        service = RedisAutomationService(config)
        if args.action == "destroy":
            service.destroy()
            print(f"REDIS_INSTANCE_NAME={config.redis_instance_name}")
            print("REDIS_STATE=DELETED")
            return 0
        result = service.create() if args.action == "create" else service.describe()
    except RedisAutomationError as exc:
        print(f"Redis command failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    emit_result(result, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
