# 스마트 타임랩스 온보딩 프로젝트

이 저장소는 `문의 등록 -> 관리자 처리 -> 완료 알림` 흐름을 자동화하는 Q&A 알림 서비스 구현물입니다.  
평가자가 가장 빠르게 이해해야 할 핵심은 아래 3가지입니다.

1. 문의의 정본 저장소는 `Notion DB`입니다.
2. `n8n`이 Notion 저장/업데이트와 메일 발송을 담당합니다.
3. `Redis`는 선택 과제인 동시 중복 등록 방지를 위해 사용합니다.

## 1. 과제 요구사항 대응 요약

현재 구현은 아래 요구사항을 포함합니다.

- 공개 문의 등록 API
- 관리자 로그인 및 관리자 문의 조회 API
- 관리자 상태 변경 API (`등록됨 -> 처리중 -> 완료됨`)
- 문의 등록 시 n8n 등록 워크플로우 호출
- 완료 처리 시 n8n 완료 워크플로우 호출
- Notion DB 저장 및 상태/처리 결과 업데이트
- 메일 발송
- 전화번호 포함 입력 검증
- `이름 + 제목` 기준 중복 등록 방지
- 동시 요청 상황에서 Redis 잠금 기반 중복 제어

제품 요구사항은 [docs/prd.md](./docs/prd.md)에 정리되어 있습니다.

## 2. 아키텍처 한눈에 보기

```text
+------------------+       HTTPS        +----------------------+
| Vercel Frontend  | -----------------> | FastAPI Backend      |
| (정적 배포 전제) |                    | on Cloud Run         |
+------------------+                    +----------+-----------+
                                                   |
                                                   | Redis lock / state
                                                   v
                                         +---------+---------+
                                         | Redis (Memorystore)|
                                         +---------+---------+
                                                   |
                                                   | webhook
                                                   v
                                         +---------+---------+
                                         | n8n on Cloud Run  |
                                         | easy mode         |
                                         +----+---------+----+
                                              |         |
                           Notion create/update|         |SMTP mail
                                              v         v
                                       +------+--+   +--+------+
                                       | Notion |   | Mail     |
                                       | DB     |   | Provider |
                                       +--------+   +---------+
```

### 역할 분리

- 프론트엔드
  - 정적 배포 전제
  - 백엔드 API만 호출
- 백엔드
  - 입력 검증
  - 관리자 인증
  - Redis 기반 잠금/상태 관리
  - n8n webhook 호출
- Redis
  - 문의 등록 상호배제
  - 중복 등록 상태 추적
  - 관리자 상태 변경 직렬화
- n8n
  - Notion 저장/업데이트
  - 관리자/문의자 메일 발송
- Notion DB
  - 문의 정본 저장소

## 3. 왜 이렇게 설계했는가

이번 과제의 핵심 제약은 두 가지였습니다.

- 요구사항상 Notion과 메일 처리는 `n8n` 안에 있어야 함
- 선택 과제상 `동시 중복 등록 방지`를 구현해야 함

Notion API만으로는 강한 중복 제어가 어렵기 때문에, 정본은 Notion에 두되 중복 제어는 Redis가 맡도록 분리했습니다.  
관련 결정은 ADR에 남겨 두었습니다.

- [ADR 인덱스](./docs/adr/000_index.md)
- [005 문의 주 저장소로 Notion DB 사용 및 Redis 동시성 제어 채택](./docs/adr/005_문의_주_저장소로_Notion_DB_사용_및_Redis_동시성_제어_채택.md)
- [006 n8n 배포 전략으로 Cloud Run easy mode 채택](./docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md)

## 4. 핵심 플로우

### 4.1 문의 등록

1. 백엔드가 입력값을 검증합니다.
2. `이름 + 제목`으로 `dedup_key`를 계산합니다.
3. Redis `lock:inquiry:{dedup_key}`를 획득합니다.
4. Redis 상태와 Notion `DedupKey`를 확인해 중복 여부를 판정합니다.
5. 중복이 아니면 백엔드가 n8n 등록 워크플로우를 호출합니다.
6. n8n이 Notion 페이지를 만들고 관리자 메일을 보냅니다.
7. 백엔드는 Redis 상태를 `confirmed`로 확정합니다.

### 4.2 관리자 상태 변경

1. 백엔드가 Redis `lock:page:{notion_page_id}`를 획득합니다.
2. `처리중`은 백엔드가 Notion 상태만 직접 반영합니다.
3. `완료됨`은 백엔드가 n8n 완료 워크플로우를 호출합니다.
4. n8n이 Notion `Status/Resolution` 업데이트와 메일 발송을 수행합니다.

중복 방지 상세 설계는 [docs/design/redis_중복_방지_플로우.md](./docs/design/redis_중복_방지_플로우.md)에 정리했습니다.

## 5. 저장소 구조

```text
backend/
  app/
    main.py              FastAPI 라우트
    services.py          문의 등록/상태 변경 비즈니스 로직
    notion_gateway.py    Notion 조회/수정
    n8n_gateway.py       n8n webhook 호출
    redis_store.py       Redis 잠금/상태 저장
automation/
  notion_*.py           Notion DB 자동화
  n8n_*.py              n8n 배포/부트스트랩/테스트 자동화
  redis_service.py      Redis 배포 자동화
  backend_*.py          backend 배포/통합 테스트 자동화
n8n/workflows/
  001_문의_등록.json
  002_문의_완료.json
docs/
  prd.md
  adr/
  design/
scripts/
  CLI 진입점 모음
tests/
  단위 테스트 및 통합 테스트 보조 코드
```

## 6. 주요 API

### 공개 API

- `POST /api/v1/inquiries`
  - 문의 등록

### 관리자 인증

- `POST /api/v1/admin/session`
- `GET /api/v1/admin/session`
- `DELETE /api/v1/admin/session`

### 관리자 문의 관리

- `GET /api/v1/admin/inquiries`
- `GET /api/v1/admin/inquiries/{notion_page_id}`
- `PATCH /api/v1/admin/inquiries/{notion_page_id}`

기본 상태 값은 `등록됨`, `처리중`, `완료됨`입니다.  
Notion 내부 매핑은 `Registered`, `In Progress`, `Completed`를 사용합니다.

## 7. 실행 및 평가용 명령

이 저장소는 `Justfile`을 단일 진입점으로 사용합니다.

### 테스트

```bash
just test
just n8n-integration-test
just backend-integration-test
```

### Notion DB 자동화

```bash
just notion-db action=ensure
just notion-db action=validate
```

### n8n

```bash
just n8n-cloud-run action=deploy
just n8n-bootstrap action=sync
```

### Redis

```bash
just redis action=create
just redis action=describe
just redis action=destroy
```

### Backend

```bash
just backend-dev
just backend-cloud-run action=deploy
```

현재 정의된 레시피는 [Justfile](./Justfile)에서 확인할 수 있습니다.

## 8. 평가자가 먼저 보면 좋은 문서

- 제품 요구사항: [docs/prd.md](./docs/prd.md)
- 아키텍처 결정 기록: [docs/adr/000_index.md](./docs/adr/000_index.md)
- Redis 중복 방지 상세: [docs/design/redis_중복_방지_플로우.md](./docs/design/redis_중복_방지_플로우.md)
- n8n 배포 절차: [docs/n8n/cloud_run_easy_mode_배포_절차.md](./docs/n8n/cloud_run_easy_mode_배포_절차.md)

## 9. 구현 상태

완료된 항목:

- Notion DB 자동 생성/검증 스크립트
- n8n Cloud Run easy mode 배포 자동화
- n8n credential/workflow bootstrap 자동화
- Redis 배포 자동화
- FastAPI backend 구현
- backend Cloud Run 배포 자동화
- live integration test 통과

현재 저장소 범위:

- 백엔드/API, 인프라 자동화, n8n 워크플로우 export는 포함
- Vercel 정적 프론트엔드 전략은 문서와 API 계약에 반영
- 실제 프론트엔드 애플리케이션 코드는 이 저장소에 포함하지 않음

실환경 통합 테스트 기준 확인된 항목:

- 문의 등록 성공
- 동일 문의 재등록 시 `duplicate_inquiry`
- 관리자 로그인 성공
- `처리중` 변경 성공
- `완료됨` 변경 성공
- Notion 최종 상태 반영 확인

## 10. 알려진 사항

- Cloud Run public URL에서 `/` 및 `/api/v1/...` 경로는 정상 응답하지만, `/healthz`는 환경에 따라 Google HTML 404를 반환하는 현상이 있었습니다.
- 그래서 live integration test는 `/healthz` 실패 시 `/`를 fallback health check로 사용합니다.
- 이 현상은 backend 내부 라우트 부재가 아니라 Cloud Run 외부 경로 처리 특성으로 보이며, 실제 API 경로 동작에는 영향이 없었습니다.

## 11. 보안 메모

- 실제 평가 환경에서는 `.env`에 들어간 비밀값을 Secret Manager 같은 별도 비밀 저장소로 분리하는 것이 맞습니다.
- n8n easy mode는 과제/데모 용도로는 충분하지만, 재배포 시 상태 유실 가능성이 있어 운영용 구성으로는 부적합합니다.
