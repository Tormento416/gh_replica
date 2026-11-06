# Architecture decision register

These decisions are defaults for implementation, not evidence that the corresponding production systems exist. Revisit only when measurements or product constraints warrant it. The user confirmed that the backbone may be public and the domain module repositories must remain private.

| ID | Decision | Reasons and benefits | Cost / rejected alternative | Revisit trigger |
| --- | --- | --- | --- | --- |
| ADR-001 | Public `gh_replica` kernel; 14 private domain repositories in `Hyrlink-dev` | Explicit user choice; reusable contracts with protected product implementations | Multi-repository CI and coordinated compatibility releases; a monorepo would simplify refactoring | Excess coordination cost or a deliberate distribution-model change |
| ADR-002 | Cell composition physically includes selected modules only | Meets the requirement to omit unpurchased software and workers | Dedicated cells cost more than a shared everything-installed process | Per-cell utilization and customer isolation requirements |
| ADR-003 | Modular core with out-of-process domain workers in production | Keeps optional dependencies out of core; independent rollout and fault boundaries | Network and operational overhead versus in-process modules | Measured latency and operational staffing; prototype uses in-process handlers only |
| ADR-004 | Python reference kernel and AI adapters; TypeScript/React UI; Go optional at measured ingress bottlenecks | Aligns with Hyrlink's Python services, TS UI, and Go gateway; avoids rewriting inference tooling | Multiple toolchains; an all-TypeScript backend is simpler for a web-only team | Profiling or team expertise warrants a different default |
| ADR-005 | JSON Schema/OpenAPI/AsyncAPI contracts and exact 0.1 core compatibility | Language-neutral, fail-closed, testable SDK generation | Exact compatibility initially requires synchronized upgrades | Contract evolution suite proves supported ranges |
| ADR-006 | Database choice pending: evaluate Supabase and MongoDB; SQLite only for local reference state | Supabase provides managed PostgreSQL with SQL transactions and row-level security; MongoDB offers a document model and managed deployment options | PostgreSQL and MongoDB require different tenant-isolation, transaction, reporting, and operations designs | Startup-program decisions and workload-specific proof of concept |
| ADR-007 | Temporal for production durable workflows | Existing retries, timers, histories, signals and long-running human tasks | Another service and workflow-version discipline; building our own durable engine adds risk | Operational cost or offline constraints prove unsuitable |
| ADR-008 | Transactional outbox plus at-least-once delivery and idempotent consumers | Honest cross-service semantics; supports reconciliation | Duplicate handling and replay tooling; no promise of global exactly-once | High measured event volume warrants Kafka or a specialized broker |
| ADR-009 | Search provider remains provisional until the database decision and benchmarks | Avoids committing to a search implementation before the primary data model is selected | Provider-native search can simplify operations but may increase coupling | Database selection and corpus, ACL, recall, latency and offline requirements |
| ADR-010 | OIDC/SAML/SCIM adapter with managed and self-hosted identity paths | Enterprise SSO and future disconnected operation | More integration testing than hard-wiring WorkOS | Customer deployment and identity requirements |
| ADR-011 | Agents propose and orchestrate; deterministic code authorizes every tool | Model errors cannot directly grant permissions or approve payments | Explicit tools and policy engineering; unrestricted agents would appear faster initially | No removal of this boundary; only optimize implementations |
| ADR-012 | NVIDIA-first evaluation behind portable provider contracts | Reuses maintained inference, retrieval, agent and evaluation infrastructure | GPU cost, licenses, product lifecycle and vendor coupling | Representative quality/cost/latency benchmark favors another implementation |
| ADR-013 | No raw model memory shared between tenants; scoped retrieval and memory | Prevents cross-tenant information flow | More indexes, ACL checks and cache partitions | No global sensitive-memory shortcut permitted |
| ADR-014 | Signed OCI artifacts, SBOMs, provenance and declared egress | Supports private modules, disconnected release bundles, and supply-chain review | Signing keys, registry and patch lifecycle require ownership | Security standards may strengthen signing requirements |
| ADR-015 | Additive migrations with staged activation and compensating recovery | Multi-service installs cannot be one database transaction | Requires compatibility windows, migration journals and recovery drills | Destructive migrations require reviewed migration campaigns |
| ADR-016 | Payroll, payment and tax providers first; internal ledger/reconciliation under our control | Avoids inventing statutory calculations and regulated payment rails | Provider cost and external dependencies; air-gapped operation requires an approved operational bridge | Qualified domain team and jurisdiction-specific certification justify native engines |
| ADR-017 | Talos/immutable Linux appliance remains a future packaging target | Preserves sovereign/private/federal options | No appliance, OS fork, or certification work in the first product slice | Proven platform operations plus a funded enterprise appliance customer |
| ADR-018 | Preserve all reference repositories; adapt only reviewed components | Prevents disrupting existing Hyrlink work and copying unknown dependencies | Requires provenance and license review | Explicit authorization to modify a particular source repository |
| ADR-019 | Human product review precedes production release; ordinary implementation and tests are automated | Fits the user's morning review model and limits operational blast radius | Not 100% autonomous commercial/legal decision-making | User-defined release policy can automate lower-risk approved changes |

## Deployment alternatives that remain available

**Dedicated tenant cell**: strongest physical module omission and fault isolation; higher idle resources, more cells to patch, more expensive small tenants. Default for strict module-absence promises, sensitive workloads, private hosting and air-gapped installations.

**Shared cell grouped by module bundle**: better utilization and lower operating cost; all tenants in a cell share its deployed code and must accept the bundle boundary. Default candidate for smaller managed SaaS tenants. Tenant permissions still apply independently.

**Single process with every module feature-flagged**: fastest to operate initially, but violates the user's physical omission requirement. Rejected as the target architecture.

**Fully separate microservice for every entity**: independent scaling, but excessive deployment, debugging, and transaction overhead before workloads justify it. Rejected; a domain module can contain a cohesive application and a few workers.

## Database evaluation

Supabase is a managed platform built on PostgreSQL; it is not a separate database engine from PostgreSQL. The existing PostgreSQL prototype is a candidate starting point for Supabase, but its migrations, database roles, connection handling, row-level security, transaction behavior, and deployment model must be validated against an actual Supabase environment before claiming compatibility.

MongoDB would require a separate implementation of the tenant directory, permissions, transaction/outbox, migrations, and data-access policies. Application-enforced tenant filtering and database permissions must be tested independently; PostgreSQL row-level security policies do not automatically carry over. Multi-document transactions require an appropriate MongoDB deployment topology.

Compare both options on tenant isolation, transaction semantics, effective-dated HR records, auditability, reporting and joins, event delivery, encryption, backup/restore, regional hosting, disconnected deployment, operational complexity, vendor terms, and total cost after startup-program decisions are known. Preserve stable domain-facing interfaces; do not assume the current SQL adapters are database-neutral.

## AI runtime alternatives

Evaluate NVIDIA agent/runtime, retrieval and inference libraries against a provider-neutral reference on the same synthetic and consented evaluation sets. Compare quality, hallucinations, authorization bypass attempts, p95 latency, tokens per task, cost per completed task, GPU utilization, offline installation and maintenance effort. Do not choose a library from a feature list alone. The running prototype deliberately uses deterministic routing and no inference provider; that keeps its security behavior reproducible before adding probabilistic planning.

## Identity boundary implementation

The first adapter uses explicitly provisioned RSA public keys and RS256 access tokens with a fixed issuer, exact audience, mandatory timestamps, bounded token lifetime, and an explicit access-token-use claim. Tenant host and organization must agree with an active server-side tenant record; permissions come from a server-side subject-and-tenant lookup, never token role claims. Unknown keys, backend failures and ambiguous hosts fail closed. Explicit keys avoid an implicit network dependency and SSRF-prone discovery, at the cost of requiring a managed key refresh/rotation process before deployment. The host must be supplied by a trusted ingress; forwarded headers are not interpreted by this adapter.

The adapter is not yet connected to a production HTTP endpoint, a real identity provider, or persistent tenancy and grant stores. Provider-specific claim mappings and key refresh, revocation and trusted-proxy policy require integration and testing before use with real data.

## HyrLink Pro recruiting adoption

The user explicitly authorized importing HyrLink Pro into the private recruiting module while preserving the source repository. A pinned source snapshot supports incremental integration and preserves the existing application; it does not imply that every copied service belongs in recruiting or is ready for release. Compared with a Git submodule, the snapshot allows changes to travel with the private recruiting repository without pushing changes to the source repository, at the cost of manually tracking upstream updates and reviewing divergence. The snapshot excludes a pre-existing nested gitlink and assistant-specific configuration; source history remains in HyrLink Pro. Review third-party rights, dependencies, data and security before release. Identity, tenant mapping, storage adapters, optional packaging and routing must be reconciled before traffic can be redirected; the database choice remains open.

## Shared backbone and post-login destinations

The backbone owns shared authentication, session, tenant and authorization infrastructure, module entitlements, the staff shell and shared orchestration interfaces. Each module owns its domain services, processes and data. Candidates enter their recruiting profile; authorized staff enter the central dashboard and can select only installed, licensed and permitted modules. Navigation does not replace enforcement at the destination. Candidate identity may span employers, so an employer's tenant membership must not be assumed to establish candidate profile ownership or access. See `ade_shared_services_and_navigation.md` for the transition and unresolved candidate-context design.

## Career breaks and experience scoring

Count documented time worked; never penalize, investigate or infer the reason for time away. Equivalent worked time receives equivalent experience-duration credit regardless of continuity, and overlapping employment periods are counted once. Tool currency, institutional knowledge and other skills require actual evidence rather than assumptions from dates. Human reviewers judge the relevance of demonstrated qualifications. Candidate correction and uncertainty handling are required. This rule applies across extraction, scoring, ranking and explanations, not only the experience calculator; the copied recruiting implementation requires a full audit before use.

When work-history dates are incomplete or the source of a stated years total cannot be established, the initial recruiting implementation withholds an experience score instead of treating an incomplete total as measured. A candidate-confirmed total and correction flow remain future work. Candidate-wide baseline scores must not substitute for an application-specific role score; the private recruiting pipeline and reports implement this for their reviewed paths, with other paths still under audit.

A position with dates that cannot be confirmed or parsed must produce a candidate-facing alert and be corrected before application submission. Missing data is a profile-correction problem, not evidence of a career break or a reason to lower a score. Candidate confirmation, self-service correction and enforcement at every application-writing boundary remain required; the initial private recruiting check covers only the current candidate application route and parseability.

Talent-pool sourcing may compare candidates who have not applied against a selected, employer-owned role when the candidate is reachable and eligible. Comparisons belong to the selected employer, candidate and role; do not replace the candidate baseline or another application's score. Recheck authorization before returning cached comparisons, and return unscored states rather than automatic rejection. The initial implementation batches lists in groups of up to 200; production freshness, consent, auditing and complete authorization still require validation.
