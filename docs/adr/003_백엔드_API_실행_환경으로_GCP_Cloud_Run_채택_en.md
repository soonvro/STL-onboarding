1. **Title**
   Adopt GCP Cloud Run as the backend API execution environment

2. **Status**
   Adopted

3. **Context**
   Because the frontend is separated as Vercel static deployment, a public HTTP API is needed to handle inquiry submission and admin functionality. The backend is responsible for validation, duplicate prevention, internal store access, admin authentication, and n8n calls. This assignment requires an infrastructure that can support container-based deployment, environment variables/secrets, and public endpoint operation without over-expanding infrastructure.

4. **Decision**
   Adopt GCP Cloud Run as the backend API execution environment. The backend is deployed as a container image and run as a standalone service separate from frontend. Cloud Run is used for public HTTP endpoint support, environment variable/secret injection, and managed scaling.

   Alternatives considered were direct VM deployment, Kubernetes-based operation, and co-locating backend on frontend platform's dynamic server features. For this scope, these options either add unnecessary complexity or blur frontend/backend boundaries and were not selected.

5. **Consequences**
   The backend can be deployed and operated simply in a managed container environment. Frontend and backend deployment units remain separated, enabling independent release cycles and easier future integration with databases and n8n. The downside is the requirement for Cloud Run-appropriate stateless service design, plus additional setup for domain, auth, and network configuration. API boundaries must also account for cold starts and inter-service separation.
