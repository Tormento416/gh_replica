# PostgreSQL identity and tenant boundary

The user is evaluating Supabase and MongoDB pending startup-program decisions. This PostgreSQL implementation is a prototype and a possible basis for Supabase, which uses PostgreSQL. It has not been validated against Supabase and does not establish a production database choice. MongoDB would require a separate implementation and isolation tests.

The identity directory stores customer host-to-tenant and WorkOS organization mappings, membership states, and explicit subject/tenant permissions. The tenant record example and outbox demonstrate transactional data isolation. Both migrations are additive foundations; they do not implement a complete HRIS schema, production migration service, or event dispatcher.

`ade_storage_contracts.py` defines provider-neutral interfaces for directory, record and outbox behavior. The WorkOS session boundary can be constructed with any implementation of the directory interface. A structural interface check verifies only method availability, not the implementation's security or transaction semantics. MongoDB and Supabase implementations must independently pass tenant-isolation, revocation, atomicity, lease, rollback and recovery tests before adoption.

## Roles and trust

- Apply the migrations in numeric order using a controlled migration owner. They are designed for a fresh database; do not blindly rerun them over existing schemas.
- The identity adapter needs a separate read-only role with `USAGE` on `ade_identity` and `SELECT` on the three directory tables. It should not have application writes or schema ownership. Control-plane access to global tenant routing metadata must be private.
- The record adapter needs a separate non-owner role with only the required `ade_core` privileges. It must not be a superuser, have `BYPASSRLS`, or inherit a privileged role. `FORCE ROW LEVEL SECURITY` does not constrain superusers or roles with `BYPASSRLS`.
- Only trusted backend code may open database connections or run SQL. The backend sets `ade.tenant_id` transaction-locally from a verified principal. PostgreSQL custom settings are not credentials; a database client allowed to issue arbitrary SQL can set another tenant value. Database network access, injection prevention, backend identity and role design are part of the isolation boundary.
- Directory lookups use a fresh connection with bounded connect/statement timeouts, parameterized SQL and no permission cache. Suspended or unknown memberships return no grants. Store exceptions are handled as authentication failure by the identity boundary.

## Atomicity and limits

The sample store writes its record and outbox row in one database transaction. If the outbox insertion fails, the record rolls back. A tenant-scoped outbox lease manager allows concurrent workers to claim disjoint events, complete a valid lease, and retry or reclaim an expired lease. Event IDs must be used by downstream consumers for deduplication: if a delivery succeeds and acknowledgment fails, the event can be delivered again. The lease manager does not send messages itself.

This is not a message broker, exactly-once guarantee, audit log, payroll ledger, encryption system, or production domain model. Direct SQL permission to insert records does not force an outbox row; callers must use the approved transaction path until stronger enforcement is implemented. Production needs a separate dispatcher role limited to the outbox, a trusted tenant-scoped worker identity, delivery adapters, retry/backoff/dead-letter policies, monitoring and idempotent consumers.

The reference consumer uses a tenant- and consumer-scoped inbox to atomically record a processed event and update a synthetic database projection. Concurrent duplicate delivery results in one database update; an event ID reused with a different record is rejected; failed projection updates roll back the inbox entry. This demonstrates deduplication for effects in the same database transaction only. External effects need their own idempotency, and incoming events must arrive through an authenticated and authorized transport. Inbox retention and replay policies remain to be designed.

No connection pool is implemented. The middleware executes identity checks in worker threads; the adapter avoids sharing database connections between threads. Production deployment needs a bounded pool, credentials and TLS, tenant-aware policies, migration/recovery procedures, encryption, operational metrics and a separate security review.

## Integration verification

The PostgreSQL tests require `ADE_TEST_DATABASE_URL` pointing to a **new, disposable cluster/database** with privileges to create the test role and schemas. They refuse to run if the identity/core schemas or test role already exist. Never point them at an existing shared or production cluster. The test role is deliberately non-owner, non-superuser and without `BYPASSRLS`.

The CI definition starts a disposable PostgreSQL service and supplies synthetic test credentials. Tests cover scoped identity grants, revocation, no-context denial, cross-tenant insert rejection, record/outbox rollback, concurrent workers, expired leases and retries. A synthetic signed HTTP request also verifies live directory grants and rejects a suspended membership. Without the variable, database integration tests are reported as skipped; a passing unit-test run alone does not establish database readiness.

The current WorkOS `.env` settings are unrelated to the database test credential. The WorkOS client ID, issuer, audience and API key are still required as appropriate for the separate provider environment before live provider verification.
