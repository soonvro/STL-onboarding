from __future__ import annotations

import argparse
import json
import sys

from automation.envfile import ConfigError, N8nIntegrationTestConfig, load_dotenv_defaults
from automation.n8n_integration_test_service import (
    N8nIntegrationTestError,
    N8nIntegrationTestResult,
    N8nIntegrationTestService,
)
from automation.notion_api import NotionClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the live n8n register/complete workflow integration test.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def emit_result(result: N8nIntegrationTestResult, *, output_format: str) -> None:
    if output_format == "json":
        json.dump(
            {
                "register_request_id": result.register_request_id,
                "complete_request_id": result.complete_request_id,
                "notion_page_id": result.notion_page_id,
                "admin_email_status": result.admin_email_status,
                "requester_email_status": result.requester_email_status,
            },
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    print("n8n integration test passed")
    print(f"REGISTER_REQUEST_ID={result.register_request_id}")
    print(f"COMPLETE_REQUEST_ID={result.complete_request_id}")
    print(f"NOTION_PAGE_ID={result.notion_page_id}")
    print(f"ADMIN_EMAIL_STATUS={result.admin_email_status}")
    print(f"REQUESTER_EMAIL_STATUS={result.requester_email_status}")


def main() -> int:
    args = parse_args()

    try:
        load_dotenv_defaults(args.env_file)
        config = N8nIntegrationTestConfig.from_environment()
        config.validate_for_action("run")
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        with NotionClient(config.notion_token, config.notion_api_version) as notion_client:
            with N8nIntegrationTestService(config, notion_client) as service:
                result = service.run()
    except N8nIntegrationTestError as exc:
        print(f"Integration test failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive top-level handler
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    emit_result(result, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
