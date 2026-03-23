1. **Title**
   n8n 배포 전략으로 Cloud Run easy mode 채택

2. **Status**
   채택

3. **Context**
   기존 ADR 002는 Notion 동기화와 메일 발송의 오케스트레이션 책임을 n8n이 가진다고 결정했지만, n8n 자체를 어디에 어떤 방식으로 배포할지는 별도로 정하지 않았다. 현재 시스템은 프론트엔드를 Vercel 정적 배포로 두고, 백엔드는 GCP Cloud Run에서 운영하며, Notion DB와 Redis를 조합해 문의 등록과 상태 관리를 구현하려는 상태다. 이번 과제는 제출용 데모 성격이 강하고, 빠르게 셋업 가능한 배포 방식을 우선하고 싶다. 또한 작업자는 n8n Cloud가 아닌 GCP Cloud Run 기반 self-host 방식 중, 공식 문서의 easy mode 절차를 사용하려는 선호를 명확히 밝혔다.

4. **Decision**
   n8n은 GCP Cloud Run의 easy mode 방식으로 배포한다. 이 배포는 제출용 데모 환경을 전제로 하며, 워크플로우 수는 `문의 등록`, `문의 완료` 두 개로 제한한다. Cloud Run 서비스는 가능하면 scale-to-zero를 피하기 위해 수동 스케일 1 설정을 고려하되, easy mode의 본질적 한계인 비영속성은 그대로 받아들인다. n8n 내부 데이터 유실 가능성을 감안해 워크플로우 정의와 필수 설정은 별도 문서 또는 export 파일로 재구성 가능하게 관리한다.

   대안으로는 n8n Cloud 사용, Cloud Run durable mode 사용, GKE 기반 self-host 구성이 있었다. n8n Cloud는 운영 편의성은 높지만 이번 선택에서는 직접 사용하지 않기로 했다. Cloud Run durable mode는 더 안정적이지만 데이터베이스와 비밀값 관리 구성이 추가되어 초기 셋업 부담이 커진다. GKE 기반 배포는 이번 과제 규모에 비해 과도하게 복잡하므로 채택하지 않는다.

5. **Consequences**
   셋업과 배포가 가장 빠르고 단순해진다. 기존 Cloud Run 기반 백엔드 전략과 인프라 결을 맞출 수 있고, 과제 시연을 위한 n8n 환경을 짧은 시간 안에 준비할 수 있다. 반면 easy mode는 n8n 데이터가 비영속적이므로 scale-to-zero, 재배포, 업데이트 시 워크플로우와 내부 상태가 유실될 수 있다. 따라서 이 배포는 운영 환경이 아니라 데모 환경으로만 취급해야 하며, 워크플로우 export와 재배포 절차 문서화가 필수다. 장기 운영 또는 안정적 재현이 필요해지면 durable mode 또는 n8n Cloud로 재검토해야 한다.
