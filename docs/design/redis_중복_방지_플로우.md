# Redis 기반 문의 중복 방지 플로우

## 1. 목적

이 문서는 [ADR 005](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/005_문의_주_저장소로_Notion_DB_사용_및_Redis_동시성_제어_채택.md)를 구현 가능한 수준으로 구체화한다.

- 문의의 정본 저장소는 Notion DB다.
- Redis는 중복 등록 방지와 상태 전이 직렬화를 위한 보조 저장소다.
- 문의 등록과 완료 처리의 외부 연동은 n8n 워크플로우가 수행한다.

이 문서의 목표는 `이름 + 제목`이 같은 문의가 동시에 들어와도 Notion DB에 중복 생성되지 않도록 하는 것이다.

## 2. 구성 요소와 책임

| 구성 요소 | 책임 |
| --- | --- |
| Vercel 정적 프론트엔드 | 문의 폼/관리자 화면 제공, 백엔드 API 호출 |
| Cloud Run 백엔드 | 입력 검증, Redis 잠금/상태 관리, n8n 호출, 관리자 인증 |
| Redis | 중복 판별 키 잠금, 등록 상태 기록, 상태 변경 직렬화 |
| n8n 등록 워크플로우 | Notion 페이지 생성, 관리자 메일 발송 |
| n8n 완료 워크플로우 | Notion 상태/처리 결과 업데이트, 문의자/관리자 메일 발송 |
| Notion DB | 문의 정본 저장소 |

## 3. 핵심 식별자

### 3.1 중복 판별 키

중복 문의 판별 기준은 `이름 + 제목`이다.

```text
normalize(value) = trim + lower-case + 연속 공백 축소
dedup_key = sha256(normalize(name) + ":" + normalize(title))
```

### 3.2 요청 식별자

- 각 등록 요청에는 `request_id`를 부여한다.
- Redis 상태 키와 n8n 호출 payload에 `request_id`를 함께 넣어 추적한다.

## 4. Redis 키 설계

| 키 | 타입 | 예시 | 용도 | TTL |
| --- | --- | --- | --- | --- |
| `lock:inquiry:{dedup_key}` | string | `lock:inquiry:abc...` | 문의 등록 상호배제 잠금 | 60초 |
| `state:inquiry:{dedup_key}` | hash | `state:inquiry:abc...` | 등록 상태 추적 | `pending` 2분, `confirmed` 30일, `failed` 5분 |
| `map:page:{notion_page_id}` | string | `map:page:123...` | Notion 페이지와 중복 판별 키 연결 | 없음 |
| `lock:page:{notion_page_id}` | string | `lock:page:123...` | 상태 변경 직렬화 잠금 | 30초 |
| `cache:inquiry:{notion_page_id}` | string/hash | `cache:inquiry:123...` | 상세 조회 캐시 | 30~60초 |
| `cache:list:{query}` | string | `cache:list:status=등록됨` | 관리자 목록 캐시 | 10~30초 |

### 4.1 `state:inquiry:{dedup_key}` 권장 필드

| 필드 | 설명 |
| --- | --- |
| `status` | `pending`, `confirmed`, `failed` |
| `request_id` | 마지막 등록 요청 식별자 |
| `notion_page_id` | Notion 생성 성공 시 페이지 ID |
| `error_code` | 최근 실패 코드 |
| `updated_at` | 마지막 상태 갱신 시각 |

## 5. 문의 등록 플로우

### 5.1 요약

1. 백엔드는 입력값을 검증한다.
2. `dedup_key`를 계산한다.
3. Redis에서 동일 키에 대한 잠금을 선점한다.
4. 선점에 성공한 요청만 n8n 등록 워크플로우를 호출한다.
5. n8n은 Notion에 `dedup_key`를 포함해 페이지를 생성한다.
6. 성공 시 Redis 상태를 `confirmed`로 확정하고 응답한다.

### 5.2 상세 단계

#### 1) 입력 검증

- 필수값, 공백-only 입력, 이메일 형식, 전화번호 형식을 검증한다.
- 검증 실패 시 Redis와 Notion에 아무 작업도 하지 않는다.

#### 2) 사전 상태 확인

- `HGETALL state:inquiry:{dedup_key}` 조회
- `status=confirmed`면 이미 등록된 문의로 간주하고 중복 응답을 반환한다.
- `status=pending`면 동일 문의가 처리 중일 가능성이 있으므로 잠금 획득을 시도한다.

#### 3) 잠금 획득

아래 명령으로 등록 잠금을 시도한다.

```text
SET lock:inquiry:{dedup_key} {token} NX EX 60
```

- 성공: 현재 요청이 생성 권한을 가진다.
- 실패: 다른 요청이 처리 중이다.

#### 4) 잠금 실패 시 처리

- 2초 이내 짧은 간격으로 `state:inquiry:{dedup_key}`를 재조회한다.
- 재조회 중 `confirmed`가 되면 중복 응답을 반환한다.
- 계속 `pending`이면 `409 processing` 또는 이에 준하는 응답을 반환한다.

#### 5) 잠금 성공 시 `pending` 기록

아래 필드를 기록한다.

```text
status=pending
request_id=<current request id>
updated_at=<now>
```

#### 6) Notion 재조회

Redis 상태가 유실되었거나 이전 요청의 응답이 끊긴 경우를 대비해, n8n 호출 전에 `dedup_key`로 Notion을 한 번 조회한다.

- 이미 같은 `dedup_key`를 가진 페이지가 있으면:
  - Redis 상태를 `confirmed`로 갱신한다.
  - `notion_page_id`를 저장한다.
  - 중복 응답을 반환한다.

#### 7) n8n 등록 워크플로우 호출

백엔드는 아래 payload를 등록 워크플로우로 보낸다.

```json
{
  "request_id": "uuid",
  "dedup_key": "sha256...",
  "name": "홍길동",
  "email": "user@example.com",
  "phone": "010-1234-5678",
  "title": "문의 제목",
  "body": "문의 본문"
}
```

n8n 등록 워크플로우는 아래 순서를 따른다.

1. Notion 페이지 생성
2. 생성 시 `dedup_key` 속성을 함께 저장
3. 관리자 메일 발송
4. 결과를 백엔드에 반환

권장 응답 형식:

```json
{
  "result": "created",
  "notion_page_id": "notion-page-id"
}
```

#### 8) 성공 처리

- Redis 상태를 `confirmed`로 바꾼다.
- `notion_page_id`를 저장한다.
- `map:page:{notion_page_id}`에 `dedup_key`를 기록한다.
- 사용자에게 등록 성공 응답을 반환한다.

#### 9) 실패 처리

- `state:inquiry:{dedup_key}`를 `failed`로 기록한다.
- `error_code`, `updated_at`를 함께 저장한다.
- 사용자는 실패 메시지를 받는다.

#### 10) 잠금 해제

잠금 해제는 토큰 검증 후 삭제하는 Lua 스크립트로 처리한다.

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
else
  return 0
end
```

## 6. 관리자 상태 변경 플로우

### 6.1 `처리중` 변경

1. 백엔드는 `lock:page:{notion_page_id}` 잠금을 획득한다.
2. n8n 또는 Notion API 경유로 상태를 `처리중`으로 갱신한다.
3. 성공 시 상세/목록 캐시를 삭제한다.
4. 잠금을 해제한다.

### 6.2 `완료됨` 변경

1. 백엔드는 `lock:page:{notion_page_id}` 잠금을 획득한다.
2. 완료 요청 payload에 `resolution`을 포함해 n8n 완료 워크플로우를 호출한다.
3. n8n은 Notion 상태를 `완료됨`으로 바꾸고 처리 결과를 기록한다.
4. n8n은 문의자 결과 메일과 관리자 완료 메일을 발송한다.
5. 성공 시 상세/목록 캐시를 삭제한다.
6. 잠금을 해제한다.

## 7. 실패 및 복구 규칙

### 7.1 Redis 잠금 만료

- 잠금을 가진 요청이 비정상 종료되면 TTL 만료 후 다음 요청이 다시 시도한다.
- 다음 요청은 곧바로 새로 생성하지 않고, 먼저 Notion을 `dedup_key`로 재조회해 기존 생성 여부를 확인한다.

### 7.2 Notion 생성 후 응답 유실

- 가장 위험한 실패 시나리오다.
- Notion에는 페이지가 생성되었지만 백엔드가 응답을 받지 못할 수 있다.
- 이 경우 다음 요청은 `dedup_key`로 Notion을 재조회해 기존 페이지를 찾아 Redis 상태를 `confirmed`로 복구해야 한다.

### 7.3 Redis 유실

- Redis가 비워져도 정본은 Notion에 있으므로 데이터 자체는 유지된다.
- 다만 Redis 상태를 잃으면 다음 요청이 `dedup_key` 기준으로 Notion을 다시 조회해 상태를 재구성해야 한다.

### 7.4 관리자 메일 발송 실패

- 권장 정책은 `Notion 페이지 생성 성공`을 등록 성공 기준으로 삼는 것이다.
- 관리자 메일만 실패한 경우 Notion 생성은 되돌리지 않고, 메일 재시도 로직으로 보완한다.

## 8. 구현 체크리스트

- Notion DB 속성에 `dedup_key`를 추가한다.
- 등록 워크플로우가 `dedup_key`를 입력으로 받고, 생성한 페이지에도 같은 값을 저장한다.
- 백엔드에서 `SET ... NX EX` 기반 잠금을 사용한다.
- 잠금 해제는 compare-and-delete Lua 스크립트로 처리한다.
- Redis `pending`, `confirmed`, `failed` 상태 전이를 구현한다.
- Redis 유실 또는 응답 유실 시 `dedup_key` 기준 Notion 재조회 복구 경로를 구현한다.
- 관리자 상태 변경 시 `lock:page:{notion_page_id}`로 직렬화한다.

## 9. 비고

- 이 설계는 중복 등록 방지를 위해 Redis를 적극 사용하지만, 관리자 조회 성능은 여전히 Notion API 특성의 영향을 받는다.
- 관리자 목록이 느려지는 문제가 커지면 별도 캐시 전략 또는 주 저장소 재검토가 필요하다.
