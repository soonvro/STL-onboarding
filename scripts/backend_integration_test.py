from __future__ import annotations

import argparse
import json
import sys

from automation.backend_integration_test_service import (
    BackendIntegrationTestError,
    BackendIntegrationTestResult,
    BackendIntegrationTestService,
)
from automation.envfile import BackendIntegrationTestConfig, ConfigError, load_dotenv_defaults
from automation.notion_api import NotionClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the deployed backend integration test against live services.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def emit_result(result: BackendIntegrationTestResult, *, output_format: str) -> None:
    if output_format == "json":
        json.dump(
            {
                "request_id": result.request_id,
                "notion_page_id": result.notion_page_id,
                "duplicate_code": result.duplicate_code,
                "final_status": result.final_status,
            },
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    print("backend integration test passed")
    print(f"REQUEST_ID={result.request_id}")
    print(f"NOTION_PAGE_ID={result.notion_page_id}")
    print(f"DUPLICATE_CODE={result.duplicate_code}")
    print(f"FINAL_STATUS={result.final_status}")


def main() -> int:
    args = parse_args()
    try:
        load_dotenv_defaults(args.env_file)
        config = BackendIntegrationTestConfig.from_environment()
        config.validate_for_action("run")
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        with NotionClient(config.notion_token, config.notion_api_version) as notion_client:
            with BackendIntegrationTestService(config, notion_client) as service:
                result = service.run()
    except BackendIntegrationTestError as exc:
        print(f"Integration test failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    emit_result(result, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
