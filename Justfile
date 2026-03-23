set dotenv-load := true
set export := true

default:
    @just --list

notion-db action="ensure":
    uv run python -m scripts.notion_db --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

n8n-cloud-run action="deploy":
    uv run python -m scripts.n8n_cloud_run --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

n8n-bootstrap action="sync":
    uv run python -m scripts.n8n_bootstrap --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

n8n-integration-test:
    uv run python -m scripts.n8n_integration_test

test:
    uv run python -m unittest discover -s tests -v
