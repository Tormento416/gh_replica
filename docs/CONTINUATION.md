# Session checkpoint and resume instructions

## Current objective

Prepare an autonomous, testable engineering foundation for the AI-native HRIS/CRM suite and a comprehensive morning-review report. `gh_replica` is the canonical public-capable backbone. Fourteen product modules are private `Hyrlink-dev` repositories. Existing Hyrlink checkouts are read-only sources.

Update: the foundation was pushed to `dev/foundation-transfer`; the user confirmed all fourteen private module repositories were created and their scaffolds pushed from Windows. The first identity-boundary implementation is on branch `ade_platform/identity-tenant-boundary`. Continue with authenticated ingress, provider-specific claim mapping and key rotation, persistent tenancy/grants, PostgreSQL isolation and outbox, and durable workflows. The older statements below describe the original checkpoint and are historical.

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
