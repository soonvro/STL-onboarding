# n8n Workflow Exports

This directory stores n8n workflow definitions as JSON export files for workflows that can be lost in a Cloud Run easy mode environment.

## File list

| File | Status | Description |
| --- | --- | --- |
| `001_문의_등록.json` | Implemented | register webhook, input validation, Notion page creation, Korean HTML+text admin email, returns success response |
| `002_문의_완료.json` | Implemented | completion webhook, input validation, Notion status/resolution update, Korean HTML+text requester/admin email, returns success response |

## Policy

- When a real workflow is created, immediately add an export file with the same name.
- Current files are importable workflow exports. After import, connect Notion credential, SMTP credential, webhook path, and sender address according to the target environment.
- Registration workflow writes only `Title`, `Name`, `Email`, `Phone`, `Body`, `DedupKey`, `Status=Registered` to Notion.
- Completion workflow writes only `Status=Completed`, `Resolution` to Notion.
- Registration workflow resolves the target Notion DB using payload `notion_database_id`.
- Completion workflow uses payload `name`, `title` to improve email readability.
- `request_id` is kept only for backend/n8n internal tracing and is not stored as a Notion property.
- Email nodes use an `SMTP` credential and send all three email types with Korean `HTML + text` templates and `emailFormat=both`.
- Even if email fails, successful Notion work still returns HTTP 200 with email status fields.
- Keep filenames aligned with this document.
- Do not store files containing credential values in the repository.
- When workflows change, update this list together with [워크플로우_export_관리_정책.md](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/n8n/워크플로우_export_관리_정책.md).
