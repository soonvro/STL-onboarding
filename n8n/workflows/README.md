# n8n Workflow Exports

이 디렉터리는 Cloud Run easy mode 환경에서 유실될 수 있는 n8n 워크플로우 정의를 JSON export 파일로 보관하는 위치다.

## 파일 목록

| 파일명 | 상태 | 설명 |
| --- | --- | --- |
| `001_문의_등록.json` | 초안 추가됨 | 등록 webhook, 입력 검증, TODO Notion 생성, TODO 관리자 메일, 응답 반환 |
| `002_문의_완료.json` | 초안 추가됨 | 완료 webhook, 입력 검증, TODO Notion 업데이트, TODO 메일 발송, 응답 반환 |

## 규칙

- 실제 워크플로우를 만들면 즉시 같은 이름으로 export 파일을 추가한다.
- 현재 파일은 import 가능한 starter export다. 실제 자격 증명과 외부 연동 노드는 import 후 교체해야 한다.
- 파일명은 이 문서의 목록과 맞춘다.
- credential 값이 포함된 파일은 저장소에 두지 않는다.
- workflow 변경 시 이 목록과 [워크플로우_export_관리_정책.md](/home/soonvro/Projects/01_Active/smart_timelabs_onboarding/docs/n8n/워크플로우_export_관리_정책.md)를 함께 갱신한다.
