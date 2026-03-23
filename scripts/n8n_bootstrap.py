from __future__ import annotations

import argparse
import json
import sys

from automation.envfile import ConfigError, N8nBootstrapConfig, load_dotenv_defaults
from automation.n8n_api import N8nApiClient
from automation.n8n_bootstrap_service import N8nBootstrapError, N8nBootstrapResult, N8nBootstrapService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap n8n credentials and workflows through the Public API.")
    parser.add_argument("--action", choices=("sync", "verify"), required=True)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--format", choices=("env", "json"), default="env")
    return parser.parse_args()


def emit_result(result: N8nBootstrapResult, *, output_format: str) -> None:
    if output_format == "json":
        json.dump(
            {
                "base_url": result.base_url,
                "notion_credential_id": result.notion_credential_id,
                "smtp_credential_id": result.smtp_credential_id,
                "register_workflow_id": result.register_workflow_id,
                "complete_workflow_id": result.complete_workflow_id,
            },
            sys.stdout,
            ensure_ascii=True,
            indent=2,
        )
        sys.stdout.write("\n")
        return

    print(f"N8N_BASE_URL={result.base_url}")
    print(f"N8N_NOTION_CREDENTIAL_ID={result.notion_credential_id}")
    print(f"N8N_SMTP_CREDENTIAL_ID={result.smtp_credential_id}")
    print(f"N8N_REGISTER_WORKFLOW_ID={result.register_workflow_id}")
    print(f"N8N_COMPLETE_WORKFLOW_ID={result.complete_workflow_id}")


def main() -> int:
    args = parse_args()

    try:
        load_dotenv_defaults(args.env_file)
        config = N8nBootstrapConfig.from_environment()
        config.validate_for_action(args.action)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        with N8nApiClient(config.n8n_base_url, config.n8n_api_key) as client:
            service = N8nBootstrapService(config, client)
            result = service.sync() if args.action == "sync" else service.verify()
    except N8nBootstrapError as exc:
        print(f"Bootstrap error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive top-level handler
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    emit_result(result, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
