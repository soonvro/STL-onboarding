# Redis-Based Duplicate Inquiry Prevention Flow

## 1. Purpose

This document concretizes [ADR 005](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/005_문의_주_저장소로_Notion_DB_사용_및_Redis_동시성_제어_채택.md) into an implementable design.

- The canonical inquiry store is the Notion DB.
- Redis is a supporting store for duplicate prevention and serializing state transitions.
- External integration for inquiry registration and completion is performed by n8n workflows.

The goal is to ensure that concurrent inquiries with the same `name + title` are not created multiple times in Notion DB.

## 2. Components and Responsibilities

| Component | Responsibility |
| --- | --- |
| Vercel static frontend | Provides inquiry form/admin screens and calls backend APIs |
| Cloud Run backend | Input validation, Redis locking/state management, n8n calls, admin authentication |
| Redis | Duplicate key locking, registration state tracking, serialization of status changes |
| n8n registration workflow | Notion page creation, admin email sending |
| n8n completion workflow | Notion status/resolution update, requester/admin email sending |
| Notion DB | Canonical inquiry store |

## 3. Key Identifiers

### 3.0 Notion Mapping

This implementation fixes Notion property names and status values in English.

| Korean concept | Notion property/value |
| --- | --- |
| Title | `Title` |
| Name | `Name` |
| Email | `Email` |
| Phone | `Phone` |
| Body | `Body` |
| Deduplication key | `DedupKey` |
| Resolution | `Resolution` |
| CreatedAt | `CreatedAt` |
| UpdatedAt | `UpdatedAt` |
| Registered | `Registered` |
| In Progress | `In Progress` |
| Completed | `Completed` |

### 3.1 Duplicate Identifier

Duplicate inquiries are identified by `name + title`.

```text
normalize(value) = trim + lower-case + collapse consecutive spaces
dedup_key = sha256(normalize(name) + ":" + normalize(title))
```

### 3.2 Request Identifier

- Each registration request gets a `request_id`.
- Include `request_id` in Redis state keys and n8n payload for tracing.
- `request_id` is for internal tracing only and is not stored as a Notion property.

## 4. Redis Key Design

| Key | Type | Example | Purpose | TTL |
| --- | --- | --- | --- | --- |
| `lock:inquiry:{dedup_key}` | string | `lock:inquiry:abc...` | registration mutual exclusion lock | 60 seconds |
| `state:inquiry:{dedup_key}` | hash | `state:inquiry:abc...` | registration state tracking | `pending` 2 min, `confirmed` 30 days, `failed` 5 min |
| `map:page:{notion_page_id}` | string | `map:page:123...` | maps Notion page to dedup key | no TTL |
| `lock:page:{notion_page_id}` | string | `lock:page:123...` | serialized status change lock | 30 seconds |
| `cache:inquiry:{notion_page_id}` | string/hash | `cache:inquiry:123...` | detail lookup cache | 30~60 seconds |
| `cache:list:{query}` | string | `cache:list:status=등록됨` | admin list cache | 10~30 seconds |

### 4.1 Recommended fields for `state:inquiry:{dedup_key}`

| Field | Description |
| --- | --- |
| `status` | `pending`, `confirmed`, `failed` |
| `request_id` | Last registration request identifier |
| `notion_page_id` | Notion page ID when creation succeeds |
| `error_code` | Most recent failure code |
| `updated_at` | Last status update timestamp |

## 5. Inquiry Registration Flow

### 5.1 Summary

1. Backend validates the input.
2. Calculates `dedup_key`.
3. Acquires lock for same key in Redis.
4. Calls n8n registration workflow only when lock acquisition succeeds.
5. n8n creates a page in Notion with `dedup_key`.
6. On success, confirms Redis state and responds to caller.

### 5.2 Detailed Steps

#### 1) Input Validation

- Validate required values, whitespace-only input, email format, and phone format.
- On validation failure, no action is taken in Redis or Notion.

#### 2) Pre-state Check

- Read `HGETALL state:inquiry:{dedup_key}`
- If `status=confirmed`, return duplicate response because an inquiry is already registered.
- If `status=pending`, attempt lock acquisition since same inquiry may currently be processing.

#### 3) Lock Acquisition

Attempt registration lock with the following command.

```text
SET lock:inquiry:{dedup_key} {token} NX EX 60
```

- Success: current request has creation authority.
- Failure: another request is currently processing.

#### 4) Handling Lock Failure

- Recheck `state:inquiry:{dedup_key}` at short intervals within 2 seconds.
- If it becomes `confirmed`, return duplicate response.
- If it remains `pending`, return `409 processing` or equivalent.

#### 5) Record `pending` on Lock Success

Write the following fields:

```text
status=pending
request_id=<current request id>
updated_at=<now>
```

#### 6) Notion Re-check

Before calling n8n, query Notion once by `dedup_key` to handle lost Redis state or dropped previous response.

- If a page with the same `dedup_key` already exists:
  - update Redis state to `confirmed`.
  - store `notion_page_id`.
  - return duplicate response.

#### 7) Call n8n Registration Workflow

Backend sends this payload to the registration workflow.

```json
{
  "request_id": "uuid",
  "dedup_key": "sha256...",
  "name": "홍길동",
  "email": "user@example.com",
  "phone": "010-1234-5678",
  "title": "Inquiry Title",
  "body": "Inquiry body"
}
```

The n8n registration workflow follows this order:

1. Create Notion page
2. Save `dedup_key` property during creation
3. Send admin email
4. Return result to backend

Recommended response format:

```json
{
  "result": "created",
  "notion_page_id": "notion-page-id"
}
```

#### 8) Success Handling

- Change Redis state to `confirmed`.
- Save `notion_page_id`.
- Store `dedup_key` in `map:page:{notion_page_id}`.
- Return registration success response to user.

#### 9) Failure Handling

- Set `state:inquiry:{dedup_key}` to `failed`.
- Save `error_code` and `updated_at`.
- User receives failure message.

#### 10) Lock Release

Use Lua script with token check-and-delete for lock release.

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
```

## 6. Admin Status Change Flow

### 6.1 Transition to `In Progress`

1. Backend acquires `lock:page:{notion_page_id}`.
2. Admin state is updated to `In Progress` via n8n or Notion API path.
3. On success, clear detail/list cache.
4. Release lock.

### 6.2 Transition to `Completed`

1. Backend acquires `lock:page:{notion_page_id}`.
2. Calls n8n completion workflow with `resolution` included in payload.
3. n8n sets Notion status to `Completed` and stores processing result.
4. n8n sends result email to inquirer and completion email to admin.
5. On success, clear detail/list cache.
6. Release lock.

## 7. Failure and Recovery Rules

### 7.1 Redis Lock Expiry

- If request holding lock terminates abnormally, the next request retries after TTL expiry.
- The next request should first re-check Notion by `dedup_key` before creating a new one.

### 7.2 Lost Response After Notion Creation

- This is the highest-risk failure scenario.
- The Notion page may be created while backend fails to receive the response.
- In this case, next request must re-check Notion by `dedup_key`, find existing page, and restore Redis state to `confirmed`.

### 7.3 Redis Data Loss

- Since the canonical source is in Notion, data itself is retained.
- If Redis is cleared, subsequent requests need to rebuild state by re-querying Notion by `dedup_key`.

### 7.4 Admin Email Failure

- Recommended policy is to treat `Notion page creation success` as registration success.
- If only admin email fails, do not roll back Notion creation; cover via email retry logic.

## 8. Implementation Checklist

- Add `dedup_key` property in Notion DB.
- Registration workflow accepts `dedup_key` and stores the same value in created page.
- Backend uses `SET ... NX EX` based lock.
- Lock release handled with compare-and-delete Lua script.
- Implement Redis state transitions for `pending`, `confirmed`, `failed`.
- Implement recovery path to re-read Notion by `dedup_key` when Redis or response is lost.
- Serialize admin status changes using `lock:page:{notion_page_id}`.

## 9. Notes

- This design heavily uses Redis for duplicate prevention, but admin read performance is still influenced by Notion API characteristics.
- If admin list slowness becomes a major issue, additional caching strategy or canonical store reconsideration is required.
