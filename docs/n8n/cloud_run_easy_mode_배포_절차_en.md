# n8n Cloud Run Easy Mode Deployment Procedure

## 1. Purpose

This document defines the deployment procedure to execute [ADR 006](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md).

- Target environment is a submission/demo environment.
- Deployment uses GCP Cloud Run easy mode per the official n8n documentation.
- This document does not cover durable mode or production-grade operational procedures.

## 2. Assumptions

- Frontend is deployed as Vercel static deployment.
- Backend API is deployed on Cloud Run.
- Notion DB is the canonical store; Redis handles duplicate prevention.
- n8n only orchestrates `inquiry registration` and `inquiry completion` workflows.

## 3. Easy Mode Usage Principles

- Easy mode is non-persistent deployment.
- n8n internal data may be lost with scale-to-zero, redeploy, and image update events.
- Therefore workflow definitions must always be managed as export files outside runtime state.
- Do not commit n8n credentials to the repository.
- Treat the service as demo-only.

## 4. Prerequisites

### 4.1 GCP Preparation

- Google Cloud Project
- Cloud Run API enabled
- `gcloud` CLI login and project selection
- Deployment region decision

### 4.2 External Integration Preparation

- Notion integration token
- Notion database/data source ID
- SMTP or other mail service credentials for email sending
- Shared secret for backend-n8n communication

### 4.3 Pre-deployment fixed values

Set the following values before deployment.

| Field | Example | Note |
| --- | --- | --- |
| n8n service name | `n8n-demo` | Cloud Run service name |
| Region | `asia-northeast3` | Seoul region recommended |
| Public URL | `https://n8n-demo-xxxxx.run.app` | Confirmed after deployment |
| Timezone | `Asia/Seoul` | Reference for workflow logs |
| Health path | `/health` | `N8N_ENDPOINT_HEALTH=health` |

## 5. Recommended Environment Variables

Easy mode is intentionally minimal, but the following values are recommended for this project.

| Variable | Value | Purpose |
| --- | --- | --- |
| `N8N_ENDPOINT_HEALTH` | `health` | Cloud Run health endpoint |
| `GENERIC_TIMEZONE` | `Asia/Seoul` | Fixed execution timezone |
| `TZ` | `Asia/Seoul` | Fixed container timezone |
| `N8N_EDITOR_BASE_URL` | Public URL | Keep UI and internal links consistent |
| `WEBHOOK_URL` | Public URL | Fixed webhook URL |

`N8N_EDITOR_BASE_URL` and `WEBHOOK_URL` should be set after the public Cloud Run URL is determined.

## 6. Deployment Procedure

### 6.1 Initial Deployment

Recommended initial deployment example:

```bash
gcloud run deploy n8n-demo \
  --image=n8nio/n8n \
  --region=asia-northeast3 \
  --allow-unauthenticated \
  --port=5678 \
  --memory=2Gi \
  --no-cpu-throttling \
  --scaling=1 \
  --set-env-vars="N8N_ENDPOINT_HEALTH=health,GENERIC_TIMEZONE=Asia/Seoul,TZ=Asia/Seoul"
```

Notes:
- `--scaling=1` reduces scale-to-zero risk.
- This setting does not prevent data loss on redeploy.
- After public URL is assigned, redeploy with `N8N_EDITOR_BASE_URL` and `WEBHOOK_URL`.

### 6.2 Applying Public URL

After initial deployment, check Cloud Run URL and apply it as follows:

```bash
gcloud run services update n8n-demo \
  --region=asia-northeast3 \
  --update-env-vars="N8N_EDITOR_BASE_URL=https://n8n-demo-xxxxx.run.app,WEBHOOK_URL=https://n8n-demo-xxxxx.run.app"
```

### 6.3 Initial Login

After deployment, initialize in this order:

1. Access n8n UI
2. Create owner account
3. Verify basic behavior before creating workflows
4. Create Notion credential
5. Create SMTP credential
6. Replace each email node `fromEmail` with actual sender address after workflow import

### 6.4 Repository Automation Path

The repository includes automation entrypoints for Cloud Run deployment and n8n bootstrap.

```bash
just n8n-cloud-run action=deploy
just n8n-bootstrap action=sync
just n8n-bootstrap action=verify
```

Recommended order:

1. Populate `.env` with GCP and SMTP/Notion values.
2. Run `just n8n-cloud-run action=deploy`.
3. Write the output `N8N_BASE_URL` back to `.env`.
4. Create owner account in n8n UI and issue API key.
5. Write `N8N_API_KEY` to `.env`.
6. Run `just n8n-bootstrap action=sync` to connect credentials/workflows.
7. Run `just n8n-bootstrap action=verify` to validate production connectivity.

## 7. Workflow Design Principles

In this project, n8n owns only the following two workflows.

| Workflow | Responsibility |
| --- | --- |
| inquiry registration | Notion page creation, admin email |
| inquiry completion | Notion status/resolution update, requester/admin email |

Common principles:
- Include `request_id` in input payload.
- Include `dedup_key` in inquiry registration.
- Include `name`, `title` for email templates in completion.
- Store `dedup_key` in Notion page.
- Workflows return success/failure in a structure that backend can interpret.
- Registration workflow uses payload `notion_database_id` to determine target DB.
- Email sending uses SMTP credential.
- Mail uses Korean `HTML + plain text` templates.

### 7.1 Notion Property Mapping

Registration workflow writes only these Notion properties:

| Notion property | Input |
| --- | --- |
| `Title` | `title` |
| `Name` | `name` |
| `Email` | `email` |
| `Phone` | `phone` |
| `Body` | `inquiry_body` |
| `DedupKey` | `dedup_key` |
| `Status` | `Registered` |
| `Resolution` | empty or unset |

Completion workflow writes only these Notion properties:

| Notion property | Input |
| --- | --- |
| `Status` | `Completed` |
| `Resolution` | `resolution` |

Rules:
- `RequestId` is not created nor written in Notion.
- `request_id` is kept only as an internal trace payload between backend and n8n.
- `CreatedAt`, `UpdatedAt` are automatic Notion attributes; do not write from workflow.

### 7.2 webhook Input Contract

Required fields for registration workflow:

| Field | Description |
| --- | --- |
| `request_id` | Internal trace request ID |
| `dedup_key` | Inquiry duplicate detection key |
| `name` | Inquirer name |
| `email` | Inquirer email |
| `phone` | Inquirer phone |
| `title` | Inquiry title |
| `body` | Inquiry body |
| `admin_email` | Admin recipient email |
| `notion_database_id` | Target Notion DB ID |

Required fields for completion workflow:

| Field | Description |
| --- | --- |
| `request_id` | Internal trace request ID |
| `notion_page_id` | Notion page ID to update |
| `name` | Inquirer name |
| `title` | Inquiry title |
| `resolution` | Inquiry answer / processing result |
| `requester_email` | Requester recipient email |
| `admin_email` | Admin recipient email |

Rules:
- `name`, `title` in completion workflow are for email template rendering only and are not stored as additional Notion properties.

### 7.3 Response Contract

Registration workflow success response returns:

| Field | Description |
| --- | --- |
| `status` | `ok` |
| `workflow` | `inquiry_register` |
| `result` | `created` |
| `request_id` | Internal trace request ID |
| `dedup_key` | Inquiry duplicate key |
| `notion_page_id` | Created Notion page ID |
| `admin_email_status` | `sent` or `failed` |

Completion workflow success response returns:

| Field | Description |
| --- | --- |
| `status` | `ok` |
| `workflow` | `inquiry_complete` |
| `result` | `completed` |
| `request_id` | Internal trace request ID |
| `notion_page_id` | Updated Notion page ID |
| `requester_email_status` | `sent` or `failed` |
| `admin_email_status` | `sent` or `failed` |

Policy:
- If Notion succeeds and only email fails, keep HTTP 200.
- In that case, only email status fields in response body should be `failed`.
- If Notion itself fails, workflow does not reach success node and returns n8n default error response.

## 8. Backend Integration Principles

- Browser never calls n8n directly.
- Only Cloud Run backend calls n8n webhooks.
- Set webhook path to an unpredictable value.
- Add shared secret header and validate it at workflow entry.

Recommended request header:

```text
X-N8N-Shared-Secret: <shared-secret>
```

Reason:
- easy mode is more likely to be publicly accessible.
- Workflows should not be callable by URL exposure alone.

## 9. Post-deployment Required Actions

After deployment or redeployment, always perform:

1. Verify n8n UI is reachable.
2. Verify owner login works.
3. Check whether credentials need re-creation.
4. Verify `inquiry registration` and `inquiry completion` workflows exist.
5. Import immediately from export files if a workflow is missing.
6. Run test webhook calls from backend.
7. Confirm Notion test page creation/update.

## 10. Operational Notes

- Before redeployments, export files must be up to date.
- Keep secret values in operations secret storage, not the repo.
- Easy mode can lose execution history and internal settings, so never rely only on n8n UI.
- If long-term operations or reproducibility become important, migrate to durable mode or n8n Cloud.

## 11. Related Documents

- [ADR 002](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/002_Notion_및_메일_오케스트레이션_책임으로_n8n_워크플로우_채택.md)
- [ADR 006](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md)
- [Redis-based duplicate prevention flow](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/design/redis_중복_방지_플로우.md)
