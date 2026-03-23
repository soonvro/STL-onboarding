from __future__ import annotations

import argparse
import json
import sys

from automation.backend_cloud_run_service import BackendCloudRunError, BackendCloudRunResult, BackendCloudRunService
from automation.envfile import BackendCloudRunConfig, ConfigError, load_dotenv_defaults


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and deploy the backend FastAPI service to Cloud Run.")
    parser.add_argument("--action", choices=("deploy", "describe"), required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--format", choices=("env", "json"), default="env")
    return parser.parse_args()


def emit_result(result: BackendCloudRunResult, *, output_format: str) -> None:
    if output_format == "json":
        json.dump(
            {
                "service_name": result.service_name,
                "region": result.region,
                "base_url": result.base_url,
                "image": result.image,
            },
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    print(f"BACKEND_BASE_URL={result.base_url}")
    print(f"BACKEND_IMAGE={result.image}")


def main() -> int:
    args = parse_args()
    try:
        load_dotenv_defaults(args.env_file)
        config = BackendCloudRunConfig.from_environment()
        config.validate_for_action(args.action)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        service = BackendCloudRunService(config)
        result = service.deploy() if args.action == "deploy" else service.describe()
    except BackendCloudRunError as exc:
        print(f"Cloud Run command failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    emit_result(result, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
