1. **Title**
   Adopt PostgreSQL as the canonical inquiry store

2. **Status**
   Superseded by ADR 005

3. **Context**
   The assignment requires Notion DB save/update, and also requires duplicate registrations for concurrent same-name/title inquiries even when Notion DB is slow. The admin page also needs reliable inquiry list and status updates. Because Notion API is an external system subject to latency and rate limits, it is difficult to assign it as a full canonical store that guarantees strong concurrency behavior. A separate decision was required for where inquiry data and status should be stored.

4. **Decision**
   Set PostgreSQL as the canonical inquiry store. Register requests, status changes, processing results, and duplicate control keys are first recorded in PostgreSQL; Notion is treated as an external system synchronized through n8n. Duplicate prevention is guaranteed through PostgreSQL constraints and transactions.

   Alternatives considered were Notion-only storage and SQLite as canonical store. Notion-only does not strongly guarantee duplicate prevention under concurrency and leaves admin listing/status management directly coupled to external API performance. SQLite is simple for single-instance demos, but inferior to PostgreSQL for concurrency control and operational scaling.

5. **Consequences**
   Inquiry truth data and state transitions can be managed stably internally, and duplicate prevention requirements are easier to satisfy at the database layer. Admin page behavior is decoupled from Notion response performance. On the downside, introducing PostgreSQL creates synchronization boundaries with Notion, so sync failures and retry policy must be handled. It also requires preparing a relational DB in operations.
