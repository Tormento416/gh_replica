# Foundation review — November 5, 2026

## Outcome

The project now has a runnable, locally verified reference backbone, fourteen separate local module repositories, a repeatable development toolchain, and an implementation plan for the full suite. This is the foundation for an automated engineering workflow and modular product; it is not a completed HRIS, production deployment, or unattended coding service.

The confirmed product direction is a public-capable `gh_replica` backbone with private `Hyrlink-dev` modules, NVIDIA-first evaluation, physically selectable module deployments, deterministic security boundaries around AI agents, and a future private/air-gapped Linux appliance path. The user's latest instruction defers remote module repository work until tomorrow.

## What changed

| Deliverable | Location | Status |
| --- | --- | --- |
| Platform kernel | `src/hyrlink_platform/runtime.py` | Implemented and locally tested reference |
| Strict module contract and resolver | `src/hyrlink_platform/contracts.py` | Implemented; exact core-version match |
| Module catalog | `catalog/*/module.json` | 14 validated synthetic module definitions |
| Platform and module agents | Runtime classes plus per-module manifests | Deterministic intent-to-tool orchestration; no LLM provider connected |
| Module scaffolding | `automation.py` and `../platform-modules/gh-module-*` relative to the backbone | 14 independent local Git repositories; no remote publication |
| Composition exporter | `hyrlink compose` | Selected metadata only; not an OCI artifact installer |
| Operator CLI and local diagnostics | `cli.py` | Runnable; loopback diagnostics only |
| Local engineering automation | Makefile, uv lock, verification runner | Implemented and executed locally |
| GitHub CI | `.github/workflows/ci.yml` | Defined; not pushed or executed on GitHub |
| Requirement and delivery plan | `docs/architecture/REQUIREMENTS_AND_ROADMAP.md` | All currently stated suite domains covered |
| Decision and alternative analysis | `docs/architecture/DECISIONS.md` | 19 recorded decisions and revisit criteria |
| Source reuse assessment | `docs/architecture/REFERENCE_REUSE.md` | Five reference checkouts inspected; no reference code copied |
| Machine-readable work queue | `docs/architecture/engineering-backlog.json` | Dependencies, states and acceptance criteria recorded |
| Session continuation | `docs/CONTINUATION.md` | Resume steps, blockers and state preserved |

## Verified behavior

The final test evidence is stored in `verification.json` beside this report. At the recorded verification run:

- 51 kernel/automation tests executed; 51 passed, 0 failures, 0 errors, 0 skips.
- All 14 module contracts validated, including their agent tool mappings.
- Each of the 14 local module repositories passed its scaffold consistency check. These are not business-feature tests.
- The synthetic demo completed a read and independently approved controlled action through the central agent and module agent, with audit-chain verification.
- A real local HTTP request verified readiness and installed-module metadata, and an undeclared domain route returned 404.
- A file-backed restart test demonstrated that a completed invocation returns its recorded result without invoking the handler a second time.
- Cross-tenant requests, missing permissions, absent modules, disabled tenant entitlements, malformed tool data, self-approval, expired approval, approval reuse and conflicting idempotency keys were rejected.
- Failed or malformed handler results require reconciliation rather than automatic repeated execution.
- The frozen dependency environment installed successfully, cached offline synchronization succeeded, and both a source distribution and wheel built successfully.
- Fresh offline wheel installation initially failed on missing registry metadata. A hash-verified local dependency wheelhouse resolved it; offline dependency installation, kernel wheel installation and an isolated import from the installed wheel then passed on Linux x86_64 / Python 3.12. This is dependency-level proof only.
- `git diff --check` passed.

Only Python 3.12.14 was tested locally. The CI matrix also declares Python 3.13; that run remains unverified. No provider sandbox, GPU, real inference model, payroll calculation, cloud deployment, production database, penetration test or regulatory certification was exercised.

## Architectural defaults

**One backbone, many owned domains.** `gh_replica` owns the common contracts, policy surface, orchestration and composition. Domain modules own their business behavior and data. No module reads another module's database directly. A private module does not become part of the public backbone merely because it uses the backbone SDK.

**Physical installation boundaries.** Dedicated tenant cells provide the strongest module-absence guarantee. Shared SaaS can group customers by deployed bundle, but a tenant cannot truthfully claim absent code while sharing a process that has it loaded for another tenant. Current composition exports demonstrate metadata omission only. Images, workers, routes, schemas, queues and frontend chunks require the real lifecycle work in Wave 2.

**Small baseline.** Use PostgreSQL, a durable workflow engine, object storage, an API/auth boundary and observability. Add search clusters, warehouses, Kafka, Kubernetes and GPUs when a measured workload or customer deployment warrants them. Module-specific dependencies belong inside module artifacts.

**Python now, language-neutral contracts.** The reference kernel favors Python to align with the existing inference, privacy and agent work and to test boundaries quickly. TypeScript/React is the UI default. The Go gateway is a candidate for production ingress after source and rights review. The earlier broad suggestion of an all-TypeScript backend was a starting option, not an implemented dependency that has been discarded.

**Deterministic policy, assisted orchestration.** AI can propose, retrieve, summarize and invoke bounded tools. It cannot create its own grants, turn external documents into instructions, issue its own human approvals, or bypass installed-module/tenant boundaries. Production plans must include budgets, deadlines, authenticated purpose, data classification, scoped retrieval and evaluation.

**Provider-backed regulated operations first.** Payroll/tax/payment integrations plus internal validation and reconciliation are the initial route. Native statutory engines and money movement would require dedicated domain ownership and jurisdiction validation. Offline operation can automate preparation, but external payment settlement and statutory submissions require a controlled approved bridge.

## How the agents align

The central agent receives an authenticated work request and selects an installed module. That module's agent maps supported domain intents to registered tools. The kernel authorizes the actor, tenant, module entitlement and permission, validates input, checks a server-recorded approval for controlled actions, applies replay rules, executes the handler, validates output, and records metadata.

Every generated module currently has `describe` and `prepare` intents. Both return scaffold metadata; `prepare` exists to exercise the approval boundary and does not send money, change personnel data, or make hiring decisions. The module templates reserve room for real domain intents and provider adapters rather than pretending those capabilities already exist.

## What the automation actually does

`make setup` restores the frozen environment. `make check` tests the kernel and validates the module catalog. `make demo` exercises the synthetic agent path. `hyrlink scaffold` produces separate module repositories without overwriting occupied paths. `hyrlink compose` exports a selected metadata bundle and content hashes. `hyrlink verify` writes machine-readable test evidence. `hyrlink repositories` prints the private GitHub creation plan; its `--apply` mode is available for intentional resumption after authorization and the user's deferral are resolved.

The CI file repeats the relevant checks on pushes and pull requests once published. It is not evidence that GitHub has already run them. There is no running background agent, auto-merger, cloud deployer or session wakeup job.

## Source reuse and NVIDIA strategy

The existing Hyrlink work informed the realm boundaries, tenant-binding tests, constrained agents, input/output gates, provider adapters and GPU fairness direction. Its READMEs also make clear that some connectors are health-only and some partner operations are not yet enabled. The new plan does not promote those scaffolds into claimed production integrations.

No tracked top-level license file was found in the five reference inventories inspected. Before copying implementations, establish provenance and rights, then preserve third-party notices and review dependencies and security boundaries. The reference repositories remain unchanged.

NVIDIA is a preferred source of maintained infrastructure, not a requirement to run GPUs everywhere. The evaluation shortlist includes NeMo agent/runtime tooling, retrieval, NIM, RAPIDS/cuDF and optimized inference services. Recheck official catalog/docs and product versions before integration. Evaluate total cost, deployment licenses, tenant isolation, quality, portability, offline support and support lifecycle. No NVIDIA skills were installed and no GPU workload was started in this work session.

## Production gaps and risks

1. The reference kernel trusts in-process `Principal` objects. It has no production OIDC adapter, host binding, SAML/SCIM, field-level grants or verified delegated identity. Never expose its invocation API directly to the Internet.
2. SQLite is local reference persistence. PostgreSQL/RLS, encrypted sensitive records, transactional outbox, external idempotency, multi-process concurrency and retention remain work.
3. The local audit chain is modifiable by a privileged database operator and is not externally anchored. It is not WORM, legal evidence custody, or a compliance claim.
4. In-process handlers are trusted code. They are not sandboxed, time-limited or independently crash-isolated. Real extension execution needs containers/microVMs/WASM, verified artifacts and enforced resources/egress.
5. A handler failure can leave real-world effects uncertain. The prototype blocks automatic replay, but operational reconciliation tooling and a durable workflow engine are still required.
6. Exact compatibility, no remote schema references and narrow synthetic inputs intentionally limit v0.1. Real domain contracts need explicit versioned evolution, richer evidence requirements and migration tests.
7. Selected manifests are copied, not deployable modules installed. Do not claim customer-ready physical code omission until the workload/image/client-bundle checks pass.
8. The public MIT backbone license remains intact. New module scaffolds carry a private all-rights-reserved notice. Confirm legal entity and commercial terms before releasing proprietary code; a private repository is not itself a license.
9. Remote repository creation returned HTTP 403 through the current GitHub integration despite the injected PAT being available. No bypass was attempted. Module remotes are deferred by the user's subsequent instruction.
10. Foundation files and module scaffolds are local, uncommitted work. They are not remotely durable until preserved through the user's environment or private repository workflow. Existing saved selection was not changed.

## Next implementation sequence

1. Review this report and accept or adjust the defaults.
2. Resume the private remote repository work when intended; establish actual creation permission and verify visibility.
3. Implement the production identity/tenant boundary and PostgreSQL data/outbox layer.
4. Add durable workflows and actual signed module installation/activation/removal.
5. Build the first CRM → recruiting → candidate → approved offer → HR/onboarding journey.
6. Add evaluated AI assistance, then expand payroll/benefits/assets, finance/AP/cases and analytics through the acceptance gates in the roadmap.

Keep the Linux/Talos appliance as a future distribution option. Containerized workloads, local service alternatives, declarative configuration, signed artifacts, versioned contracts and tested recovery preserve that option now. A military-wide or FedRAMP deployment requires a funded reliability/compliance program and multiple failure domains; node count alone is not a capacity or authorization argument.

## Morning review points

The most useful review is whether these defaults match the product: public kernel/private modules; customer-specific installation cells; Python reference kernel with TypeScript UI and optional Go ingress; provider-backed payroll/payments; candidate transparency and core HR lifecycle as the first end-to-end slice; NVIDIA candidates selected by evidence; production release through reviewed policy.

Routine implementation choices do not need another permission loop. Customer policy, jurisdiction, legal authority, production credentials and consequential business decisions require authoritative information rather than guessed defaults. Those requirements are captured in the roadmap and need not block foundation engineering.

## Continuity

The session was not stopped by a five-hour limit. No supported reminder or task scheduler was available, so no automatic restart was created or promised. `docs/CONTINUATION.md` provides durable resume instructions; a new user turn or supported product automation must actually resume work.
