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
