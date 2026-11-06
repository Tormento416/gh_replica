# Shared services, module ownership and post-login journeys

## Target journeys

All users authenticate through the backbone identity boundary. The backbone resolves a verified identity and effective context, evaluates the applicable license and access policy, then selects a logical destination. A candidate lands on their recruiting profile. An authorized staff member lands on the central dashboard and sees only modules installed in the deployment, enabled under the customer's license, and permitted by their identity and access grants. Selecting a module opens its registered entry point; every destination and API independently enforces access. A UI tile or redirect is never an authorization decision.

A person can hold both candidate and staff identities or permissions; do not infer privilege from the requested landing page. A server-authorized context switch can select an available audience without merging the two. Candidates may apply to multiple employers and retain a profile without being staff members of those employers. Candidate identity, consent, profile ownership and employer-scoped application access need explicit design before real identity or tenant routing. The current organization-bound reference identity adapter and development navigation do not solve that model. If candidate profile ownership eventually belongs to the separate candidate-experience module, use a versioned contract and route there while keeping recruiting application workflows in recruiting.

## Ownership map

| Capability | Backbone shared service | Recruiting module responsibility |
| --- | --- | --- |
| Authentication and sessions | WorkOS/OIDC integration, session lifecycle, trusted ingress and identity verification | Consume a trusted, audience-scoped identity; enforce domain access on every request |
| Tenant and policy | Tenant registry, organization binding, module installation, licensing, IAM/ACL decisions and audit context | Enforce candidate, recruiter and requisition-level access; never derive grants from request headers or model output |
| Application shell and routing | Staff dashboard, permitted module catalog, approved entry-point registry and safe routing | Supply recruiting entry points and candidate profile experience through versioned contracts |
| Workflow and agents | Workflow execution, queue/event infrastructure, approvals, observability and policy-enforced agent/tool runtime | Recruiting agent, candidate intake, sourcing, requisitions, screening and hiring workflow rules |
| Data and integrations | Database infrastructure abstractions, secret management, encryption interfaces, event transport and integration framework | Own recruiting schemas, migrations, data-access adapters, event contracts and recruiting-specific connectors |
| AI capabilities | Provider-neutral model gateway, budgets, evaluation, telemetry and data controls | Recruiting prompts, tools, evaluations and human-review requirements; never self-grant permissions |

Shared infrastructure is a capability contract, not a mandate that every module use a shared database or process. Modules retain ownership of their data, migrations and business rules. An uninstalled module must not contribute its deployable workloads or frontend chunks; a tenant license alone is not installation. Candidate-facing availability and data ownership require a separate license/consent policy rather than assuming an employer staff entitlement.

## HyrLink Pro transition

The private recruiting snapshot includes a Next.js application, Go gateway, candidate and enterprise Python APIs, workers, inference components and Supabase-specific schemas. The following sequence preserves behavior while moving boundaries:

1. Inventory the existing login, callback, cookie, tenant resolution and gateway paths; introduce backbone-backed adapters while preserving the legacy paths for staged testing. Treat the current direct WorkOS and Supabase authentication as legacy integration points, not additional trusted identities.
2. Connect backbone identity, session and policy to the module through short-lived, audience-bound credentials or another reviewed service-to-service mechanism. The module verifies the credential and applies object-level policy; no forwarded client-supplied identity headers or browser secrets.
3. Separate shared infrastructure clients from recruiting-specific logic. Define interfaces for orchestration, audit, messaging, model access and storage before switching implementations. Preserve data migrations and test tenant isolation in whichever database is chosen.
4. Register candidate profile and recruiter entry points; route staff through the dashboard. Use controlled server configuration and preserve existing URL/callback compatibility during migration.
5. Package and test the recruiting service set independently. Prove absent modules have no routes, services, workers, migrations or browser chunks in a customer deployment.

The existing prototype `ade_navigation.Navigation` produces logical destinations and a filtered catalog from caller-provided trusted state. It is not a production login, license authority, dashboard, policy engine or redirect endpoint, and its static snapshots do not handle revocation. It requires a tenant-bound principal, so it is not sufficient for the multi-employer candidate use case. Real implementation must add identity-context selection, live grants, license and session revocation, safe redirect/return-path handling, and end-to-end independent enforcement.
