1. **Title**
   Adopt n8n workflows for Notion and email orchestration responsibilities

2. **Status**
   Adopted

3. **Context**
   The assignment requires calling an n8n workflow when inquiry is submitted and that workflow must perform Notion DB save and admin email sending. It also requires n8n workflow for completion processing, and that workflow must send requester result email, admin completion email, and update Notion status/result. We needed a clear boundary decision for which component owns final external integration execution.

4. **Decision**
   Orchestration responsibilities for Notion synchronization and email sending are owned by n8n workflows. The system uses two n8n workflows: `inquiry registration` and `inquiry completion`; the application backend handles only input validation, internal state persistence, and workflow invocation. Direct Notion calls and email sending logic are not kept as main backend responsibilities.

   Alternatives included backend-direct handling of Notion and email, and direct frontend-to-Notion/email communication. Both were rejected. Backend-direct handling conflicts with assignment text, and frontend direct calls to Notion/email were excluded due to secret exposure and security concerns.

5. **Consequences**
   Responsibilities are aligned with assignment requirements and system boundaries are clarified. External orchestration can be visualized and modified in n8n, and registration/completion processing is separated into dedicated workflows. However, n8n becomes an additional operational component, adding availability, deployment, and secret-management responsibilities. Clear request/response contracts and retry/failure policies between backend and n8n are also required.
