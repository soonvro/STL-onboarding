from __future__ import annotations

import argparse
import json
import sys

from automation.envfile import ConfigError, NotionAutomationConfig, load_dotenv_defaults
from automation.notion_api import NotionClient
from automation.notion_db_service import NotionDatabaseService, NotionDbAutomationError, NotionDbResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure or validate the Notion database schema.")
    parser.add_argument("--action", choices=("ensure", "validate"), required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--format", choices=("env", "json"), default="env")
    return parser.parse_args()


def emit_result(result: NotionDbResult, *, output_format: str) -> None:
    if output_format == "json":
        payload = {
            "database_id": result.database_id,
            "data_source_id": result.data_source_id,
            "database_title": result.database_title,
            "created": result.created,
            "warnings": result.warnings,
        }
        json.dump(payload, sys.stdout, ensure_ascii=True, indent=2)
        sys.stdout.write("\n")
        return

    print(f"NOTION_DATABASE_ID={result.database_id}")
    print(f"NOTION_DATA_SOURCE_ID={result.data_source_id}")


def main() -> int:
    args = parse_args()

    try:
        load_dotenv_defaults(args.env_file)
        config = NotionAutomationConfig.from_environment()
        config.validate_for_action(args.action)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        with NotionClient(config.notion_token, config.notion_api_version) as client:
            service = NotionDatabaseService(config, client)
            if args.action == "ensure":
                result = service.ensure()
            else:
                result = service.validate()
    except NotionDbAutomationError as exc:
        print(f"Automation error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive top-level handler
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    emit_result(result, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
