1. **Title**
   Adopt Vercel static deployment for frontend strategy

2. **Status**
   Adopted

3. **Context**
   The primary user touchpoints are public inquiry submission and admin pages. Users only need browser access to enter and view information, while integrations requiring secrets (Notion API token, n8n webhook key, email credentials) must not be exposed to the browser. The operator is most comfortable with static frontend deployment, and scope should focus on meeting assignment requirements. Therefore a separation where frontend handles rendering/input and backend handles dynamic processing and security is appropriate.

4. **Decision**
   Build the frontend as static assets and deploy it on Vercel. Browsers receive only static pages and JavaScript, and inquiry/admin features call a separate backend HTTP API. No server-side rendering, server actions, or secret-driven external integrations are placed in frontend.

   Alternatives included serving frontend from the same backend server and using Vercel dynamic server features. For this assignment, static frontend deployment is sufficient for requirements and simplifies deployment and operations, so it was preferred.

5. **Consequences**
   Frontend deployment is simplified and can take advantage of static hosting. Frontend can focus on UI/UX while security-sensitive flows stay in backend boundaries. The downside is the need for boundary setup such as CORS, API URL management, and admin auth integration across separate deployments. Also, external integration cannot be fully completed in browser-only mode, so a backend API is required.
