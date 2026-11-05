# Architecture decision register

These decisions are defaults for implementation, not evidence that the corresponding production systems exist. Revisit only when measurements or product constraints warrant it. The user confirmed that the backbone may be public and the domain module repositories must remain private.

| ID | Decision | Reasons and benefits | Cost / rejected alternative | Revisit trigger |
| --- | --- | --- | --- | --- |
| ADR-001 | Public `gh_replica` kernel; 14 private domain repositories in `Hyrlink-dev` | Explicit user choice; reusable contracts with protected product implementations | Multi-repository CI and coordinated compatibility releases; a monorepo would simplify refactoring | Excess coordination cost or a deliberate distribution-model change |
| ADR-002 | Cell composition physically includes selected modules only | Meets the requirement to omit unpurchased software and workers | Dedicated cells cost more than a shared everything-installed process | Per-cell utilization and customer isolation requirements |
| ADR-003 | Modular core with out-of-process domain workers in production | Keeps optional dependencies out of core; independent rollout and fault boundaries | Network and operational overhead versus in-process modules | Measured latency and operational staffing; prototype uses in-process handlers only |
| ADR-004 | Python reference kernel and AI adapters; TypeScript/React UI; Go optional at measured ingress bottlenecks | Aligns with Hyrlink's Python services, TS UI, and Go gateway; avoids rewriting inference tooling | Multiple toolchains; an all-TypeScript backend is simpler for a web-only team | Profiling or team expertise warrants a different default |
| ADR-005 | JSON Schema/OpenAPI/AsyncAPI contracts and exact 0.1 core compatibility | Language-neutral, fail-closed, testable SDK generation | Exact compatibility initially requires synchronized upgrades | Contract evolution suite proves supported ranges |
| ADR-006 | PostgreSQL for production records; SQLite only for local reference state | PostgreSQL supports transactions, effective dating, constraints, RLS and outbox | Managed operation, tuning, migrations; SQLite lacks distributed writer semantics | Workload evidence requires partitioning or dedicated stores |
| ADR-007 | Temporal for production durable workflows | Existing retries, timers, histories, signals and long-running human tasks | Another service and workflow-version discipline; building our own durable engine adds risk | Operational cost or offline constraints prove unsuitable |
| ADR-008 | Transactional outbox plus at-least-once delivery and idempotent consumers | Honest cross-service semantics; supports reconciliation | Duplicate handling and replay tooling; no promise of global exactly-once | High measured event volume warrants Kafka or a specialized broker |
| ADR-009 | Start with PostgreSQL search/pgvector where adequate; external search optional | Reduces baseline service count and module bloat | Lower ceiling than dedicated search systems | Corpus, ACL filtering, recall or latency fails benchmark |
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

## AI runtime alternatives

Evaluate NVIDIA agent/runtime, retrieval and inference libraries against a provider-neutral reference on the same synthetic and consented evaluation sets. Compare quality, hallucinations, authorization bypass attempts, p95 latency, tokens per task, cost per completed task, GPU utilization, offline installation and maintenance effort. Do not choose a library from a feature list alone. The running prototype deliberately uses deterministic routing and no inference provider; that keeps its security behavior reproducible before adding probabilistic planning.

## Identity boundary implementation

The first adapter uses explicitly provisioned RSA public keys and RS256 access tokens with a fixed issuer, exact audience, mandatory timestamps, bounded token lifetime, and an explicit access-token-use claim. Tenant host and organization must agree with an active server-side tenant record; permissions come from a server-side subject-and-tenant lookup, never token role claims. Unknown keys, backend failures and ambiguous hosts fail closed. Explicit keys avoid an implicit network dependency and SSRF-prone discovery, at the cost of requiring a managed key refresh/rotation process before deployment. The host must be supplied by a trusted ingress; forwarded headers are not interpreted by this adapter.

The adapter is not yet connected to a production HTTP endpoint, a real identity provider, or persistent tenancy and grant stores. Provider-specific claim mappings and key refresh, revocation and trusted-proxy policy require integration and testing before use with real data.
