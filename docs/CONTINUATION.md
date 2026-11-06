# Session checkpoint and resume instructions

## Current objective

Prepare an autonomous, testable engineering foundation for the AI-native HRIS/CRM suite and a comprehensive morning-review report. `gh_replica` is the canonical public-capable backbone. Fourteen product modules are private `Hyrlink-dev` repositories. Existing Hyrlink checkouts are read-only sources.

Update: the foundation was pushed to `dev/foundation-transfer`; the user confirmed all fourteen private module repositories were created and their scaffolds pushed from Windows. The first identity-boundary implementation is on branch `ade_platform/identity-tenant-boundary`. Continue with authenticated ingress, provider-specific claim mapping and key rotation, persistent tenancy/grants, PostgreSQL isolation and outbox, and durable workflows. The older statements below describe the original checkpoint and are historical.

WorkOS is the chosen provider. This platform uses a separate WorkOS organization or environment from the existing Hyrlink endpoint; never assume the existing client, issuer, keys or credentials. See `docs/security/ade_workos_configuration.md`. A fixed-host AuthKit session signing-key loader and bounded key snapshot are implemented and tested. Actual token profile compatibility, live sign-in, production ingress, and persisted grants remain open.

Latest continuation: the key store and tenant boundary are connected through reference ASGI middleware. Synthetic tests exercise signed requests, spoofed forwarded hosts, duplicate headers, revoked grants and unknown signing keys. WorkOS values were not present in this cloud runtime; token-profile compatibility and live authentication remain unverified. Next implement thread-safe persistent tenant/grant stores, real provider-specific token validation, trusted ingress configuration and production integration tests. Do not expose the reference middleware as production-ready.

Database continuation: PostgreSQL migrations now define an identity directory, tenant-scoped example records and a transactional outbox; adapters and restricted-role integration tests are implemented. See `docs/security/ade_database_boundary.md`. They do not constitute a production storage deployment. Next: migration version management, deployment roles/TLS, durable outbox dispatch and idempotency, encrypted real domain records, integration of the directory into a running service, and a controlled provider test once WorkOS configuration is available.

Outbox continuation: tenant-scoped event leasing, completion, retry and expired-lease reclaim are implemented and tested using concurrent workers. They provide at-least-once leasing, not a network delivery adapter or exactly-once processing. The separate staging client can reach its public WorkOS signing-key endpoint; actual login and token-profile compatibility are still unverified. Next implement a real bounded delivery adapter and deduplication, migration management, production roles/TLS and the provider sign-in integration.

Database selection update: the user is comparing Supabase and MongoDB while startup-program decisions are pending. Supabase is PostgreSQL-based; existing PostgreSQL work is a candidate, not a confirmed Supabase integration or final database choice. Keep interfaces provider-neutral and assess both options as described in ADR-006 before committing to a production data layer.

Latest storage continuation: provider-neutral directory, record and outbox interfaces now exist. A signed synthetic HTTP request has been tested through the identity middleware and a real PostgreSQL directory, including cross-tenant rejection and immediate membership suspension. The PostgreSQL test instance is disposable. Supabase and MongoDB adapters and full production security/recovery remain unverified.

The current leading brand candidate is Adelyr, not yet finalized; see `docs/architecture/ade_brand_direction.md`. A synthetic consumer inbox now demonstrates tenant-scoped, transactional database-effect deduplication for concurrent and failed deliveries. Network transport, external side-effect idempotency, event retention and production deployment remain future work.

Migration checkpoint: a PostgreSQL journal now verifies migration sequence and checksums, refuses untracked pre-existing schemas, serializes runners with a database lock and atomically records each successful migration. `migration-plan` and `migration-apply` use `ADE_MIGRATION_DSN`; only explicitly selected, trusted databases should be used. Tested on disposable PostgreSQL. Provider selection remains open and this does not establish MongoDB support or Supabase compatibility. Next: authenticated bounded event delivery and a private CRM vertical slice.

Delivery checkpoint: the reference outbox can now deliver tenant-scoped metadata to one configured allowlisted HTTPS destination using a bearer credential and a stable idempotency key. It rejects insecure TLS and redirects, schedules retries on send failure, and records uncertain acknowledgments. Local TLS and PostgreSQL tests pass. The receiver, dead-letter policy, secret rotation and deployed worker remain to be built. Next: inspect the existing private CRM module checkout, preserve local work, and build a bounded domain slice only in the private module repository.

CRM checkpoint: the private `Hyrlink-dev/gh-module-client-crm` repository has branch `ade_crm/account-foundation` at commit `327a25d`. It adds a tenant-scoped account service, per-actor idempotency, a synthetic event, duplicate detection and a separately authorized duplicate override. Thirteen module tests pass. Its current repository is in-memory only; a durable local development adapter, production provider adapter, trusted platform tool context and audit are still required. The earlier uncommitted cloud scaffold remains untouched.

CRM durability checkpoint: commit `b73c950` on the same private branch adds a SQLite development adapter. Account, idempotency and event changes commit together; tests cover restart, concurrent connections and failed-event rollback. SQLite has no database-enforced row-level security and is not a production provider choice. Seventeen module tests pass. Next: propagate trusted platform principal and request ID into module tool handlers without relying on caller-supplied identity.

Trusted-context checkpoint: the reference kernel can register a contextual handler that receives the already-verified principal and server request ID only after module, tenant, permission, approval and input-schema checks. Existing payload-only handlers remain supported. Tests verify that denied requests never reach the contextual handler and that replays do not execute it twice. This is in-process trusted code, not a plugin sandbox or production ingress.

CRM integration checkpoint: the private CRM branch `ade_crm/account-foundation` now exposes `account-create` and `account-get` as contextual tools. Creation requires the platform's independent approval, receives the trusted principal and request ID from the platform, and persists its development account and event atomically. Nineteen module tests passed with the backbone installed, including tenant isolation and replay after kernel restart. The SQLite adapter remains development-only; duplicate override is not exposed as an agent tool. Module CI pins the backbone revision; remote CI status remains to be checked.

CRM contact checkpoint: commit `f90018f` adds tenant-scoped contacts, development persistence and approved contextual create/read tools. Twenty-seven tests passed with the backbone installed, including concurrent retries, transactional rollback, approval, and cross-tenant account-link rejection. Contact names and emails are stored unencrypted in the development adapter; only synthetic data is permitted. The production database provider, encryption, real identity integration, retention and contact duplicate-override workflow remain open. Next: an approved client hiring request with a traceable recruiting handoff.

Audit-link checkpoint: controlled tool-start records now include the validated approval ID and request ID, allowing an operator to correlate the action with its independent approval. This does not make the local hash chain tamper-proof or replace a production audit service.

## Completed locally

- Architecture, repository ownership, deployment-cell strategy and future Linux/Talos appliance note.
- Python reference kernel: strict module contracts, explicit dependency closure, installed-module registry, tenant grants, deterministic platform/module agents, permission enforcement, independent expiring single-use approvals, durable local operation replay and hash-linked audit records.
- Fourteen JSON module manifests and fourteen separate local Git scaffolds under `../platform-modules`, relative to the backbone checkout.
- CLI for catalog validation, scaffold generation, metadata composition, synthetic agent demo, loopback diagnostics and private GitHub repository planning/provisioning.
- Frozen dependency lockfile, Makefile and CI workflow definition.
- Adversarial/behavioral local tests plus module scaffold consistency tests.
- Decision register, suite requirements, phased roadmap, reference assessment, operational limitations and review report.

## Important state

Existing README/AGENTS/architecture changes predate the current session; preserve them. New work remains local and uncommitted for review. Module repositories have unborn local `main` branches; an origin URL is a target, not evidence of remote existence. Nothing has been pushed, deployed, published, or added to the environment's saved repository selection.

The PAT variable `gh_replica_fg_pat` became available in the new runtime, but a fixed GitHub organization repository-creation request still received an integration-level HTTP 403. Do not log, inspect, copy or persist the token. Do not keep retrying without a meaningful authorization change. The user then explicitly deferred remote module work until tomorrow. Respect that deferral.

## Resume sequence

1. Read `AGENTS.md`, `docs/reports/FOUNDATION_REVIEW.md`, and `docs/architecture/DECISIONS.md`.
2. Inspect `git status` and existing `../platform-modules` directories. Do not overwrite local work or create worktrees.
3. From the `gh_replica` checkout, run `uv sync --frozen`, then `uv run --frozen python scripts/dev.py check` and `uv run --frozen python scripts/dev.py demo`. These commands also support the intended Windows location, `D:\HRIS_project\gh_replica`.
4. Apply the user's review: yes, no, or requested adjustments. Do not restart the architecture from scratch.
5. When remote module creation is resumed, use the private repository manifest; verify actual authorization and visibility. Preserve local scaffolds, publish them only through the intended private destinations, and record remote evidence separately from local state.
6. Begin Wave 1 from `REQUIREMENTS_AND_ROADMAP.md`: production identity/tenant boundary, PostgreSQL/RLS and outbox, durable workflows, then real module artifact lifecycle. Add scoped acceptance tests with each implementation slice.

## Session-limit handling

No callable scheduling or reminder tool was available in this session. This checkpoint is durable context, not a scheduled wakeup. It cannot restart an agent after a five-hour product limit. A new user turn or supported product automation must resume the work. Do not claim background progress while no agent is running.

### CRM hiring-request checkpoint

The private CRM branch `ade_crm/account-foundation` at `2d1dede` adds synthetic tenant-scoped hiring requests, with controlled platform approval, per-actor idempotency, and an identifier-only handoff event committed atomically in the development SQLite store. The 33 CRM tests pass locally, including platform approval, cross-tenant isolation, concurrent replay, and transaction rollback. The GitHub workflow pins backbone commit `82ddf4d`. The recruiting consumer, production persistence, secure transport and a production request-details API remain to be built; the event alone does not create a job. No customer data should be used with this development adapter.

### Recruiting handoff checkpoint

Private recruiting branch `ade_recruiting/hiring-inbox` at `3a942ca` adds a synthetic SQLite inbox for the CRM hiring-request event. It deduplicates retries, rejects conflicting IDs, scopes records by tenant and records them as pending details; its six local tests pass. The HyrLink Pro posting guide informed the decision that a brief client request must not automatically publish a role. The CRM outbox and recruiting inbox are not yet connected; trusted transport identity, tenant binding, an authorized details API, provider-specific durable storage and full requisition controls remain open. The reference inbox must not be exposed or used for real data.

CRM GitHub Actions confirmed all 33 tests passed on `2d1dede`. Candidate product name Adelyr remains provisional; database provider selection remains pending startup-program decisions.

### HyrLink recruiting source checkpoint

The private recruiting branch `ade_recruiting/hiring-inbox` at `6a05c1b` contains a pinned HyrLink Pro source snapshot and the assessment `docs/ade_hyrlink_module_assessment.md`. The reference checkout was left unchanged. The new route planner is an offline prototype, not live gateway enforcement. The snapshot omits an existing nested gitlink and assistant-specific configuration. Nine module tests pass locally; the full copied application and its Go gateway were not built in this environment (the Go compiler is unavailable). Its production identity, tenant, storage, packaging and routing integration remain open. See the private assessment for acceptance gates and source provenance.

### Shared services and landing journeys

The user confirmed backbone-owned shared orchestration, authentication and the staff dashboard; recruiting keeps its unique workflows and candidate profile. Candidates land on their profile, while staff choose from installed, licensed and individually permitted modules. `docs/architecture/ade_shared_services_and_navigation.md` maps ownership and migration, including the unresolved multi-employer candidate identity model. `ade_navigation.py` is a synthetic logical-navigation prototype, not production authentication, a UI or live license enforcement.

### Career-break requirement

The user specified that gaps are not scrutinized: count time worked, not time away, and leave the relevance of evidenced skills to human review. Recruiting branch `ade_recruiting/hiring-inbox` commit `0b8aa14` documents the policy and tests the existing experience-duration component with equal eight-year histories, one containing a three-year break. The 11 local recruiting tests pass. The regression does not establish fairness of the full scoring pipeline; partial dates, missing roles, parsing, ranking, summaries and other continuity or recency proxies remain to be assessed. See the private module's `docs/ade_experience_scoring_policy.md`.
