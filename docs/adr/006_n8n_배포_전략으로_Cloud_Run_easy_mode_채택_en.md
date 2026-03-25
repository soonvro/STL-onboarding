1. **Title**
   Adopt n8n Cloud Run easy mode as the deployment strategy

2. **Status**
   Adopted

3. **Context**
   ADR 002 decided that n8n should own orchestration responsibilities for Notion sync and email sending, but it did not separately define how and where to deploy n8n itself. The current system is designed with Vercel static deployment for the frontend and backend on GCP Cloud Run, and Notion DB + Redis for inquiry storage and state handling. This assignment has a strong demo/submit orientation and prioritizes a quickly set-up deployment strategy. The operator also explicitly expressed preference for the official GCP Cloud Run-based self-hosted approach using easy mode, rather than n8n Cloud.

4. **Decision**
   Deploy n8n with GCP Cloud Run easy mode. This deployment is scoped to a demo environment and limits workflows to `inquiry registration` and `inquiry completion`. For Cloud Run service, manual scaling to 1 is considered to avoid scale-to-zero when possible, while the inherent non-persistent nature of easy mode is fully accepted. To account for possible workflow definition loss, workflow definitions and essential settings are managed as export files or documented for reconstruction.

   Alternatives considered were n8n Cloud, Cloud Run durable mode, and self-hosting on GKE. n8n Cloud offered better operational convenience but was not selected in this setup. Cloud Run durable mode is more reliable, but adds extra setup overhead for database and secret management. GKE deployment is overly complex for this assignment size, so it was not selected.

5. **Consequences**
   Setup and deployment become faster and simpler. The setup aligns with existing Cloud Run-based backend strategy and enables a working n8n demo environment quickly. On the other hand, easy mode is non-persistent, so workflow definitions and internal state may be lost on scale-to-zero, redeploy, or image update. Therefore this deployment must be treated as demo-only, with mandatory export file maintenance and redeploy procedures. If long-term operations or reliable reproducibility become necessary, migration to durable mode or n8n Cloud should be re-evaluated.
