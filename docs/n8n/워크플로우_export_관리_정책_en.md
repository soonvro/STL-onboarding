# n8n Workflow Export Management Policy

## 1. Purpose

Cloud Run easy mode can lose internal n8n data, so workflow definitions should be managed in the repository rather than only inside the runtime. This document defines how export files are stored and updated.

## 2. Storage Location

Workflow export files are stored in the directory below.

- [workflows/README.md](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/n8n/workflows/README.md)

The actual JSON export files follow this naming format:

- `001_문의_등록.json`
- `002_문의_완료.json`

## 3. Management Principles

- Export immediately when creating a workflow.
- Refresh export files on the same day when meaningful modifications are made.
- Export files should always match the latest state in n8n UI.
- Do not include credential values in export files.
- Restore secrets manually in production or from a separate secret manager.

## 4. Export Timing

Export files must be refreshed in the following cases:

- New workflow creation
- Node add/remove
- webhook path change
- Notion property mapping change
- Mail subject/body change
- Error branch change
- Response payload format change

## 5. Recommended Update Procedure

1. Update workflow in n8n.
2. Verify normal operation by running tests.
3. Export workflow to JSON.
4. Overwrite existing file.
5. If the change is significant, update related design docs or ADRs as well.

## 6. Filename Rules

- The number indicates workflow inventory order.
- Keep filenames in Korean.
- Replace spaces with `_`.
- Match workflow name and filename as closely as possible.

## 7. Import Recovery Procedure

If workflows disappear after easy mode redeployment, recover in this order.

1. Sign in to n8n UI.
2. Recreate Notion credential and Mail credential.
3. Import `001_문의_등록.json`.
4. Import `002_문의_완료.json`.
5. Reconnect each workflow credential.
6. Verify webhook path and shared-secret validation nodes.
7. Validate registration/completion flows with test payloads.

## 8. Review Checklist

- Does the repository contain the latest export files?
- Are workflow names aligned with filenames?
- Is dedup_key storage logic reflected in exports?
- Do registration/completion response payloads match backend contract?
- Are credential values absent from export files?

## 9. Related Documents

- [n8n Cloud Run easy mode deployment guide](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/n8n/cloud_run_easy_mode_배포_절차.md)
- [ADR 006](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md)
