# n8n Workflow Exports

이 디렉터리는 Cloud Run easy mode 환경에서 유실될 수 있는 n8n 워크플로우 정의를 JSON export 파일로 보관하는 위치다.

## 파일 목록

| 파일명 | 상태 | 설명 |
| --- | --- | --- |
| `001_문의_등록.json` | 구현됨 | 등록 webhook, 입력 검증, Notion 페이지 생성, 한국어 HTML+text 관리자 메일, 성공 응답 반환 |
| `002_문의_완료.json` | 구현됨 | 완료 webhook, 입력 검증, Notion 상태/처리결과 업데이트, 한국어 HTML+text 문의자/관리자 메일, 성공 응답 반환 |

## 규칙

- 실제 워크플로우를 만들면 즉시 같은 이름으로 export 파일을 추가한다.
- 현재 파일은 import 가능한 workflow export다. import 후 Notion credential, SMTP credential, webhook path, 발신 주소를 환경에 맞게 연결해야 한다.
- 등록 workflow의 Notion 생성은 `Title`, `Name`, `Email`, `Phone`, `Body`, `DedupKey`, `Status=Registered`만 쓴다.
- 완료 workflow의 Notion 업데이트는 `Status=Completed`, `Resolution`만 쓴다.
- 등록 workflow는 payload의 `notion_database_id`를 사용해 대상 Notion DB를 결정한다.
- 완료 workflow는 메일 가독성을 위해 payload의 `name`, `title`을 함께 사용한다.
- `request_id`는 백엔드/n8n 내부 추적용으로만 유지하고, Notion 속성으로 저장하지 않는다.
- 메일 노드는 `SMTP` credential을 사용하며, 세 메일 모두 한국어 `HTML + text` 템플릿과 `emailFormat=both`를 사용한다.
- 메일 실패 시에도 Notion 작업이 성공했다면 HTTP 200과 메일 상태 필드를 반환한다.
- 파일명은 이 문서의 목록과 맞춘다.
- credential 값이 포함된 파일은 저장소에 두지 않는다.
- workflow 변경 시 이 목록과 [워크플로우_export_관리_정책.md](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/n8n/워크플로우_export_관리_정책.md)를 함께 갱신한다.
