1. **Title**
   Adopt Notion DB as canonical inquiry store and Redis-based concurrency control

2. **Status**
   Adopted

3. **Context**
   The assignment requires core external integration for registration and completion to be handled in n8n workflows, with results written back to Notion DB. It also requires that concurrent inquiries with the same `name + title` are not registered when Notion DB is slow. ADR 004 had previously adopted PostgreSQL as the canonical store, but current discussions introduced a constraint to keep Notion DB as canonical and avoid adding a separate relational store. We therefore needed a new decision on how to strengthen concurrency control in that context.

4. **Decision**
   Keep Notion DB as canonical inquiry store and use Redis as an auxiliary store for concurrency control and duplicate prevention. On inquiry registration, the application computes a dedup key from `name + title`, performs atomic lock/state updates in Redis, then calls the n8n registration workflow. n8n writes the dedup key to Notion page creation; when it confirms creation, Redis state is updated to confirmed. State transitions are also serialized by locking by Notion page in Redis before calling the completion workflow.

   Alternatives considered included using PostgreSQL as canonical storage, using Notion only, and using Redis as canonical store. PostgreSQL provides strong constraints easiest but requires a separate relational DB. Notion-only storage cannot robustly guarantee duplicate prevention under concurrent submissions. Redis-only storage does not align with the Notion-first requirements and incurs greater operational overhead to operate as canonical write store.

5. **Consequences**
   This choice preserves the Notion-first requirements while using Redis atomic operations to reduce race conditions during concurrent registrations. It incorporates duplicate prevention requirements without an extra relational DB, and Redis state allows differentiation of in-progress/confirmed/failed registration outcomes. However, because canonical data is in Notion and concurrency control in Redis, recovery procedures across both systems are required. Cases like lock expiry, n8n timeout, and response loss after Notion write must recover by re-reading Notion with dedup key. Admin listing and status reads remain subject to Notion API performance and limits.
