# n8n Cloud Run easy mode 배포 절차

## 1. 목적

이 문서는 [ADR 006](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md)을 실행하기 위한 배포 절차를 정리한다.

- 대상 환경은 제출용 데모다.
- 배포 방식은 n8n 공식 문서의 GCP Cloud Run easy mode다.
- 이 문서는 durable mode나 운영 환경 절차를 다루지 않는다.

## 2. 전제

- 프론트엔드는 Vercel 정적 배포다.
- 백엔드 API는 Cloud Run에 배포된다.
- 문의 정본은 Notion DB이며, 중복 방지는 Redis가 담당한다.
- n8n은 `문의 등록`, `문의 완료` 워크플로우의 오케스트레이션만 맡는다.

## 3. easy mode 사용 원칙

- easy mode는 비영속 배포다.
- scale-to-zero, 재배포, 이미지 업데이트 시 n8n 내부 데이터가 유실될 수 있다.
- 따라서 워크플로우 정의는 항상 export 파일로 별도 보관해야 한다.
- n8n 내부 자격 증명은 저장소에 커밋하지 않는다.
- 서비스는 데모 환경으로만 취급한다.

## 4. 준비 항목

### 4.1 GCP 준비

- Google Cloud Project
- Cloud Run API 활성화
- `gcloud` CLI 로그인 및 프로젝트 선택
- 배포 리전 결정

### 4.2 외부 연동 준비

- Notion integration token
- Notion database/data source ID
- 메일 발송용 SMTP 또는 메일 서비스 자격 증명
- 백엔드와 n8n 사이에 사용할 shared secret

### 4.3 배포 전 확정값

아래 값은 배포 전에 고정한다.

| 항목 | 예시 | 비고 |
| --- | --- | --- |
| n8n 서비스명 | `n8n-demo` | Cloud Run 서비스명 |
| 리전 | `asia-northeast3` | 서울 리전 권장 |
| 공개 URL | `https://n8n-demo-xxxxx.run.app` | 배포 후 확정 |
| 타임존 | `Asia/Seoul` | 워크플로우 로그 기준 |
| health path | `/health` | `N8N_ENDPOINT_HEALTH=health` |

## 5. 권장 환경 변수

easy mode 최소 구성은 단순하지만, 이번 과제에서는 아래 값을 권장한다.

| 변수 | 값 | 목적 |
| --- | --- | --- |
| `N8N_ENDPOINT_HEALTH` | `health` | Cloud Run health endpoint |
| `GENERIC_TIMEZONE` | `Asia/Seoul` | 실행 시간대 고정 |
| `TZ` | `Asia/Seoul` | 컨테이너 시간대 고정 |
| `N8N_EDITOR_BASE_URL` | 공개 URL | UI 및 내부 링크 일관성 |
| `WEBHOOK_URL` | 공개 URL | webhook URL 고정 |

`N8N_EDITOR_BASE_URL`와 `WEBHOOK_URL`은 실제 Cloud Run 공개 URL이 정해진 뒤 값이 확정된다.

## 6. 배포 절차

### 6.1 최초 배포

권장 배포 예시는 아래와 같다.

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

설명:
- `--scaling=1`은 scale-to-zero를 줄이기 위한 선택이다.
- 이 설정은 재배포 시 데이터 유실을 막지 못한다.
- 공개 URL이 확정되면 `N8N_EDITOR_BASE_URL`, `WEBHOOK_URL`을 반영해 다시 배포한다.

### 6.2 공개 URL 반영

최초 배포 후 Cloud Run URL을 확인한 뒤 아래 값을 반영한다.

```bash
gcloud run services update n8n-demo \
  --region=asia-northeast3 \
  --update-env-vars="N8N_EDITOR_BASE_URL=https://n8n-demo-xxxxx.run.app,WEBHOOK_URL=https://n8n-demo-xxxxx.run.app"
```

### 6.3 초기 로그인

배포 직후 아래 순서로 초기화한다.

1. n8n UI 접속
2. owner 계정 생성
3. 워크플로우 생성 전 기본 동작 확인
4. Notion credential 생성
5. SMTP credential 생성
6. workflow import 후 각 메일 노드의 `fromEmail` 값을 실제 발신 주소로 교체

### 6.4 저장소 자동화 경로

저장소에는 Cloud Run 배포와 n8n bootstrap을 위한 자동화 진입점이 있다.

```bash
just n8n-cloud-run action=deploy
just n8n-bootstrap action=sync
just n8n-bootstrap action=verify
```

권장 순서:

1. `.env`에 GCP와 SMTP/Notion 값을 채운다.
2. `just n8n-cloud-run action=deploy`를 실행한다.
3. 출력된 `N8N_BASE_URL`을 `.env`에 반영한다.
4. n8n UI에서 owner 계정을 생성하고 API key를 발급한다.
5. `N8N_API_KEY`를 `.env`에 반영한다.
6. `just n8n-bootstrap action=sync`로 credential/workflow를 연결한다.
7. `just n8n-bootstrap action=verify`로 실환경 연결 상태를 점검한다.

## 7. 워크플로우 구성 원칙

이번 과제에서 n8n은 아래 두 워크플로우만 가진다.

| 워크플로우 | 책임 |
| --- | --- |
| 문의 등록 | Notion 페이지 생성, 관리자 메일 발송 |
| 문의 완료 | Notion 상태/처리 결과 업데이트, 문의자/관리자 메일 발송 |

공통 원칙:
- 입력 payload에는 `request_id`를 포함한다.
- 문의 등록에는 `dedup_key`를 포함한다.
- 문의 완료에는 메일 템플릿용 `name`, `title`을 포함한다.
- Notion 페이지에는 `dedup_key`를 저장한다.
- 워크플로우는 성공/실패 결과를 백엔드가 해석 가능한 구조로 반환한다.
- 등록 workflow는 payload의 `notion_database_id`를 사용해 대상 DB를 결정한다.
- 메일 발송은 SMTP credential을 사용한다.
- 메일은 한국어 `HTML + plain text` 템플릿으로 발송한다.

### 7.1 Notion 속성 매핑

등록 워크플로우의 Notion 생성은 아래 속성만 사용한다.

| Notion 속성 | 입력값 |
| --- | --- |
| `Title` | `title` |
| `Name` | `name` |
| `Email` | `email` |
| `Phone` | `phone` |
| `Body` | `inquiry_body` |
| `DedupKey` | `dedup_key` |
| `Status` | `Registered` |
| `Resolution` | 빈 값 또는 미설정 |

완료 워크플로우의 Notion 업데이트는 아래 속성만 사용한다.

| Notion 속성 | 입력값 |
| --- | --- |
| `Status` | `Completed` |
| `Resolution` | `resolution` |

규칙:
- `RequestId`는 Notion 속성으로 만들지 않고, 쓰지도 않는다.
- `request_id`는 백엔드와 n8n 사이의 내부 추적용 payload 값으로만 유지한다.
- `CreatedAt`, `UpdatedAt`은 Notion 자동 속성이므로 workflow에서 직접 쓰지 않는다.

### 7.2 webhook 입력 규약

등록 workflow의 필수 입력 필드는 아래와 같다.

| 필드 | 설명 |
| --- | --- |
| `request_id` | 내부 추적용 요청 ID |
| `dedup_key` | 문의 중복 판별 키 |
| `name` | 문의자 이름 |
| `email` | 문의자 이메일 |
| `phone` | 문의자 연락처 |
| `title` | 문의 제목 |
| `body` | 문의 본문 |
| `admin_email` | 관리자 수신 주소 |
| `notion_database_id` | 대상 Notion DB ID |

완료 workflow의 필수 입력 필드는 아래와 같다.

| 필드 | 설명 |
| --- | --- |
| `request_id` | 내부 추적용 요청 ID |
| `notion_page_id` | 갱신 대상 Notion 페이지 ID |
| `name` | 문의자 이름 |
| `title` | 문의 제목 |
| `resolution` | 문의 답변/처리 결과 |
| `requester_email` | 문의자 수신 주소 |
| `admin_email` | 관리자 수신 주소 |

규칙:
- 완료 workflow의 `name`, `title`은 메일 템플릿 렌더링용으로만 사용하고, 추가 Notion 속성으로 저장하지 않는다.

### 7.3 응답 규약

등록 workflow의 성공 응답은 아래 필드를 반환한다.

| 필드 | 설명 |
| --- | --- |
| `status` | `ok` |
| `workflow` | `inquiry_register` |
| `result` | `created` |
| `request_id` | 내부 추적용 요청 ID |
| `dedup_key` | 문의 중복 판별 키 |
| `notion_page_id` | 생성된 Notion 페이지 ID |
| `admin_email_status` | `sent` 또는 `failed` |

완료 workflow의 성공 응답은 아래 필드를 반환한다.

| 필드 | 설명 |
| --- | --- |
| `status` | `ok` |
| `workflow` | `inquiry_complete` |
| `result` | `completed` |
| `request_id` | 내부 추적용 요청 ID |
| `notion_page_id` | 갱신된 Notion 페이지 ID |
| `requester_email_status` | `sent` 또는 `failed` |
| `admin_email_status` | `sent` 또는 `failed` |

정책:
- Notion 작업이 성공하고 메일만 실패하면 HTTP 200을 유지한다.
- 이 경우 응답 본문의 메일 상태 필드만 `failed`로 내려간다.
- Notion 작업 자체가 실패하면 workflow는 성공 응답 노드에 도달하지 않고 n8n 기본 오류 응답을 반환한다.

## 8. 백엔드 연동 원칙

- 브라우저가 n8n을 직접 호출하지 않는다.
- Cloud Run 백엔드만 n8n webhook을 호출한다.
- webhook path는 예측하기 어려운 값으로 설정한다.
- 추가로 shared secret 헤더를 붙이고, 워크플로우 초입에서 검증한다.

권장 요청 헤더:

```text
X-N8N-Shared-Secret: <shared-secret>
```

권장 이유:
- easy mode는 서비스가 공개 접근 가능 상태가 되기 쉽다.
- URL 노출만으로 등록/완료 워크플로우가 호출되면 안 된다.

## 9. 배포 후 필수 작업

배포 또는 재배포가 끝나면 항상 아래를 수행한다.

1. n8n UI 접속 가능 여부 확인
2. owner 로그인 확인
3. credential 재생성 필요 여부 확인
4. `문의 등록`, `문의 완료` 워크플로우 존재 여부 확인
5. 워크플로우가 없으면 export 파일에서 즉시 import
6. 백엔드에서 test webhook 호출
7. Notion 테스트 페이지 생성/수정 확인

## 10. 운영 주의사항

- 재배포 전에 반드시 워크플로우 export 파일을 최신화한다.
- credential 값은 repo가 아니라 운영 비밀 저장소에 기록한다.
- easy mode에서는 실행 이력과 내부 설정도 유실될 수 있으므로 n8n UI만 믿지 않는다.
- 장기 운영이나 재현 가능성이 중요해지면 durable mode 또는 n8n Cloud로 전환한다.

## 11. 관련 문서

- [ADR 002](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/002_Notion_및_메일_오케스트레이션_책임으로_n8n_워크플로우_채택.md)
- [ADR 006](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md)
- [Redis 기반 문의 중복 방지 플로우](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/design/redis_중복_방지_플로우.md)
