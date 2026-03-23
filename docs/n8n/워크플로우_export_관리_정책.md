# n8n 워크플로우 export 관리 정책

## 1. 목적

Cloud Run easy mode는 n8n 내부 데이터가 유실될 수 있으므로, 워크플로우 정의를 저장소 밖이 아닌 저장소 안에서 관리해야 한다. 이 문서는 export 파일을 어떤 방식으로 보관하고 갱신할지 정의한다.

## 2. 저장 위치

워크플로우 export 파일은 아래 디렉터리에 둔다.

- [workflows/README.md](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/n8n/workflows/README.md)

실제 JSON export 파일은 다음 형식을 따른다.

- `001_문의_등록.json`
- `002_문의_완료.json`

## 3. 관리 원칙

- 워크플로우를 새로 만들면 즉시 export 한다.
- 의미 있는 수정이 있으면 같은 날 export 파일을 갱신한다.
- export 파일은 n8n UI의 최신 상태와 항상 같아야 한다.
- 자격 증명 값은 export 파일에 포함시키지 않는다.
- 비밀값은 운영 환경에서 수동 재입력하거나 별도 비밀 저장소에서 복구한다.

## 4. export 시점

아래 경우에는 반드시 export 파일을 갱신한다.

- 신규 워크플로우 생성
- 노드 추가/삭제
- webhook path 변경
- Notion 속성 매핑 변경
- 메일 제목/본문 변경
- 오류 처리 분기 변경
- 응답 payload 형식 변경

## 5. 권장 관리 절차

1. n8n에서 워크플로우를 수정한다.
2. 테스트 실행으로 정상 동작을 확인한다.
3. 워크플로우를 JSON으로 export 한다.
4. 기존 파일을 덮어쓴다.
5. 변경 이유가 크면 관련 설계 문서 또는 ADR을 함께 갱신한다.

## 6. 파일명 규칙

- 숫자는 워크플로우 인벤토리 순서를 의미한다.
- 파일명은 한국어로 유지한다.
- 공백은 `_`로 바꾼다.
- workflow 이름과 파일명은 최대한 일치시킨다.

## 7. import 복구 절차

easy mode 재배포 후 워크플로우가 사라졌다면 아래 순서로 복구한다.

1. n8n UI에 로그인한다.
2. Notion credential과 메일 credential을 다시 만든다.
3. `001_문의_등록.json`을 import 한다.
4. `002_문의_완료.json`을 import 한다.
5. 각 workflow의 credential 연결을 다시 지정한다.
6. webhook path와 shared secret 검증 노드를 확인한다.
7. 테스트 payload로 등록/완료 플로우를 검증한다.

## 8. 검토 체크리스트

- 최신 export 파일이 저장소에 있는가
- workflow 이름과 파일명이 일치하는가
- Notion `dedup_key` 저장 로직이 export에 반영되어 있는가
- 등록/완료 응답 payload가 백엔드 계약과 일치하는가
- credential 값이 export 파일에 남지 않았는가

## 9. 관련 문서

- [n8n Cloud Run easy mode 배포 절차](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/n8n/cloud_run_easy_mode_배포_절차.md)
- [ADR 006](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/adr/006_n8n_배포_전략으로_Cloud_Run_easy_mode_채택.md)
