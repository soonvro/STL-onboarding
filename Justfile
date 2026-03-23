set dotenv-load := true
set export := true

default:
    @just --list

notion-db action="ensure":
    uv run python -m scripts.notion_db --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

test:
    uv run python -m unittest discover -s tests -v
