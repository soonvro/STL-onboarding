set dotenv-load := true
set export := true

default:
    @just --list

deps-lock:
    uv lock

notion-db action="ensure":
    uv run python -m scripts.notion_db --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

n8n-cloud-run action="deploy":
    uv run python -m scripts.n8n_cloud_run --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

n8n-bootstrap action="sync":
    uv run python -m scripts.n8n_bootstrap --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

n8n-integration-test:
    uv run python -m scripts.n8n_integration_test

backend-dev:
    uv run uvicorn backend.app.asgi:app --host 0.0.0.0 --port 8000 --reload

frontend-dev port="3000":
    uv run python -m scripts.frontend_dev_server --port "$(printf '%s' '{{port}}' | sed 's/^port=//')"

frontend-vercel-link:
    npx vercel link --cwd frontend

frontend-vercel-deploy:
    npx vercel --cwd frontend --yes

frontend-vercel-deploy-prod:
    npx vercel --cwd frontend --prod --yes

backend-test:
    uv run python -m unittest discover -s tests -p 'test_backend*.py' -v

redis action="describe":
    uv run python -m scripts.redis_instance --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

backend-cloud-run action="deploy":
    uv run python -m scripts.backend_cloud_run --action "$(printf '%s' '{{action}}' | sed 's/^action=//')"

backend-proxy port="8081":
    gcloud run services proxy "${BACKEND_SERVICE_NAME:-qna-backend}" --project "${GCP_PROJECT_ID}" --region "${GCP_REGION:-asia-northeast3}" --port "$(printf '%s' '{{port}}' | sed 's/^port=//')"

backend-docker-run port="8080":
    docker run --rm --env-file .env -p "$(printf '%s' '{{port}}' | sed 's/^port=//')":8080 "${BACKEND_IMAGE:-gcr.io/${GCP_PROJECT_ID}/qna-backend}"

backend-integration-test:
    uv run python -m scripts.backend_integration_test

test:
    uv run python -m unittest discover -s tests -v
