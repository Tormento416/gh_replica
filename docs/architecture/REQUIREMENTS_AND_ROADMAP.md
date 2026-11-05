# Product requirements and execution roadmap

This is the initial implementation baseline. It covers the currently stated suite and identifies decisions that need domain discovery. It does not claim complete knowledge of every customer's policy, jurisdiction, integration, or future requirement. Each feature must acquire acceptance tests and a data/permission contract before implementation.

## Product outcome

Measure reduction in human handling time and corrections for a fixed, comparable workload. The user's benchmark is 25 representatives taking five business days versus three handling equivalent work with fewer errors. At equal working hours that implies approximately 88% less labor, not necessarily faster elapsed time. Baseline the workload mix before setting automation promises. Aim for high straight-through rates on routine transactions; preserve accountable human decisions for sensitive and consequential cases.

## Domain specification baseline

| Module | First entities / records | Agent responsibilities | Initial acceptance gate |
| --- | --- | --- | --- |
| Client CRM | Account, contact, opportunity, service agreement, requisition request | Prepare follow-ups, summarize account state, coordinate approved service work | An approved client request produces a traceable recruiting handoff without duplicate accounts |
| Recruiting | Requisition, posting, application, interview, scorecard, offer | Intake, document extraction, scheduling, evidence summaries, offer preparation | Requisition → application → structured interview → human-reviewed offer with consent and audit |
| Candidate experience | Candidate-owned profile, consent, evidence, preference, status event | Profile assistance, skills evidence, application reuse, status explanation | Candidate can export/delete eligible data, see accurate status and revoke optional sharing |
| Core HR | Worker, employment, position, organization unit, effective-dated compensation | Prepare lifecycle changes, identify incomplete records, coordinate corrections | Accepted offer creates exactly one employment record, with effective-date history and tenant isolation |
| Lifecycle | Journey, checklist, assignment, document acknowledgment, provisioning task | Schedule onboarding/offboarding, follow up, escalate blocked dependencies | New hire reaches an evidence-backed ready state; departure revokes access and tracks return tasks |
| Benefits | Plan, eligibility rule, enrollment, dependent, life event, carrier discrepancy | Explain approved plans, validate completeness, prepare changes | Eligibility and enrollment round-trip reconciles with a provider sandbox and preserves history |
| Payroll/time | Time entry, leave, pay period, run, earnings, deductions, variance | Prepare inputs, flag outliers, reconcile approved runs | Golden payroll fixtures reconcile exactly with an approved provider; no autonomous release of funds |
| Accounts payable | Vendor, PO, invoice, matching result, approval, payment instruction | Extract invoices, detect duplicates, suggest coding, resolve exceptions | Duplicate/replayed invoices do not double-pay; independent approval precedes provider submission |
| Assets/logistics | Asset, stock item, assignment, shipment, return, custody event | Prepare allocation, track shipments, escalate delays, coordinate recovery | Onboarding and departure reconcile assigned assets, custody and delivery evidence |
| Financials | Journal, account, budget, allocation, billing item, reconciliation | Prepare accruals and explanations, detect inconsistencies, coordinate close | Balanced journals, controlled corrections, closed-period rules and traceable source events |
| Cases/incidents | Case, allegation, evidence, access policy, investigation task, finding | Triage, timelines, deadline checks, cited summaries, escalation | Case ACLs prevent unrelated HR access; human investigator owns findings and outcomes |
| Analytics | Semantic metric, process event, dataset, report, forecast | Explain measures, identify bottlenecks, suggest tested improvements | Metric reconciles to authoritative records and cannot bypass tenant/field permissions |
| Employee service | Request, article, conversation, service task, notification preference | Scoped self-service, cited policy answers, routing, SLA follow-up | Employee sees only authorized records; unavailable answers are escalated, not invented |
| Integration packs | Connection metadata, capability, mapping, webhook receipt, delivery attempt | Select approved adapter actions and route reconciliation work | Signatures, replay defense, retries, fixed endpoints and provider sandbox contract tests pass |

Workflow automation, AI orchestration, and administration/security are backbone services. User interfaces for them may be packaged as separately licensed features. Connector packs must eventually be separate artifacts per provider: installing one connector must not pull every connector dependency into a tenant cell.

## Shared contracts

**Identity**: principal ID, actor type, authenticated issuer, tenant binding, allowed purposes, role/attribute grants, expiry and delegated identity. Never derive authority from model text or a caller-controlled tenant header alone.

**Commands**: command ID, idempotency key, tenant, authenticated actor reference, purpose, module, action version, validated input, correlation ID and deadline. Commands request work; they are not proof of authorization.

**Events**: event ID, type, version, tenant, aggregate ID/version, occurrence time, producer, correlation/causation IDs and classified payload. Events are emitted with the domain transaction through an outbox. Consumers deduplicate, handle version changes and report reconciliation gaps.

**Money/time**: ISO currency plus integer minor units or database decimal; never binary floating-point money. Preserve original timezone and UTC instants, legal entity and jurisdiction, daylight-saving behavior, effective dates and payroll cutoff semantics.

**Documents**: tenant-scoped object IDs, classification, owner, consent/legal basis, malware scan state, signed access grant, retention/hold state and deletion receipt. Search uses the same ACL and deletion policies as the source.

**Agent request**: permitted intent, scoped context references, tool catalog version, deadline, token/cost/tool-call budget, approval requirements, model/prompt version and evaluation trace. Model output is an untrusted proposal, checked against the installed allowlist.

## Lifecycle state machines

Module release: draft → contract-validated → scanned → signed → staged → compatibility-tested → approved-for-release.

Cell installation: planned → artifacts-verified → migrations-applied → workloads-starting → health-verified → routes-active. A failed stage produces a journal entry and explicit recovery task. Never advertise activation before health and migration gates pass.

Removal: block new work → drain/cancel workflows → export/retain data under policy → revoke tools/routes/subscriptions → remove workloads → verify physical absence. Retention may preserve encrypted data without keeping module execution installed. Legal holds override deletion.

Business workflow: created → validated → ready → running → waiting-on-human or waiting-on-external → completed, failed, cancelled or reconciliation-required. Cross-domain operations use sagas with explicit compensation; not every real-world action can be undone.

Agent execution: authorized context → bounded proposal → deterministic policy → evidence/approval if required → registered tool → schema-validated result → audit/metrics. Failure, ambiguity, policy conflict, unavailable evidence and exhausted budget lead to escalation, not privilege escalation.

## Implementation waves and exit gates

### Wave 0 — Contract and reference foundation (current work)

Deliver the public kernel, manifests, composition resolver, deterministic agents, local audit/approval/idempotency store, CLI, local module scaffolds, frozen dependencies, tests, CI configuration, decision register and continuation plan. Exit: all local checks pass and current limitations are explicit. This is a development foundation only.

### Wave 1 — Production platform boundary

Implement an authenticated API facade, OIDC/tenant-host binding, policy adapter, provider-neutral storage interfaces, encrypted sensitive fields, transaction/outbox support, Temporal workers, secrets interfaces, per-tenant rate limits and OpenTelemetry. Evaluate Supabase and MongoDB before choosing the production data layer; validate the existing PostgreSQL/RLS prototype against Supabase if selected, or implement and test an equivalent MongoDB isolation and transaction design. Build a common accessible TypeScript/React design system and module-aware navigation. Do not import optional UI bundles into the backbone shell. Exit: multi-tenant adversarial tests, workflow crash recovery, data backup/restore and end-to-end audit continuity pass in an isolated integration environment.

### Wave 2 — Real module lifecycle

Implement private artifact publishing, digest-pinned composition, signature verification, dependency/version matrix, staged deployment, additive migration journals, activation/draining/removal, and SBOM/provenance checks. Exit: a tenant cell includes no unselected module image, worker, queue, route, schema migration or frontend chunk; failed upgrades recover without losing committed data.

### Wave 3 — First business journey

Build CRM request → recruiting requisition → candidate consent/application → structured interview → approved offer → core HR worker → onboarding checklist. Add assets and payroll/benefits readiness as integration tasks before expanding into full native administration. Exit: existing golden fixtures and a user-reviewed synthetic scenario complete with no cross-tenant exposure, duplicated worker or missing approval.

### Wave 4 — AI assistance with evaluation

Qualify NeMo/NVIDIA candidates; add a provider gateway, typed plans, scoped retrieval, data classification/egress controls, prompt versioning, cost accounting and per-tenant admission fairness. Begin with read-only summaries and drafting. Exit: groundedness, extraction accuracy, injection/authorization attack resistance, cost and abstention gates pass; deterministic workflow remains operable without an LLM.

### Wave 5 — Workforce operations

Extend effective-dated HR, benefits, leave/time, provider-backed payroll, employee service, assets and logistics. Exit: authoritative sandbox reconciliation, jurisdiction fixtures, accessibility review, retention/deletion and operator exception playbooks are validated by domain owners.

### Wave 6 — Financial and case operations

Build AP, journal/reconciliation interfaces, budgets, billing, incidents and restricted case work. Exit: separation of duties, sensitive case ACLs, balanced ledger invariants, replay-safe payments, evidence retention and independent investigator review pass.

### Wave 7 — Scale and enterprise release

Load-test real workload mixes; introduce search, warehouse or broker services only when measurements justify them. Harden supply chain, disaster recovery, SSO/SCIM, tenant export, accessibility, regional placement, upgrade support and support operations. Exit: agreed capacity, SLOs, security assessment, recovery objectives and incident response exercises pass.

### Wave 8 — Disconnected appliance discovery

Build a signed offline artifact mirror, local identity/model/observability bundle, licensing mechanism that does not require constant egress, and offline update/recovery workflows. Evaluate Talos and hardware profiles. Exit: disconnected install, patch, rollback, credential rotation and multi-site restore demonstration. Compliance authorization and hardware certification are separate programs, not automatic consequences of this design.

## Proposed targets to validate, not current claims

| Area | Initial target / method |
| --- | --- |
| Interactive API latency | p95 under 300 ms excluding inference and upstream-provider waits, at a specified representative load |
| Availability | 99.9% initial managed-service objective; price and topology for higher tiers established through reliability testing |
| Recovery | Provisional RPO 15 minutes / RTO 4 hours for initial enterprise tier; financial data may need tighter objectives |
| Automation | Compare human touches, time per case, first-pass accuracy and rework against a baseline; never use unsupported 99% marketing claims |
| Module absence | Inspect image inventory, processes, routes, subscriptions, queues, artifacts and client bundles for unselected modules |
| AI quality | Evaluate per task: extraction field accuracy, source-groundedness, unsupported claims, refusals, adverse impact, latency and cost |
| Tenant safety | Zero successful cross-tenant reads/writes in adversarial integration tests; access logs and source ACL checks required |
| Release quality | Contract, migration, rollback, retention, security, dependency and accessible journey checks required per affected module |

## Automated engineering loop

1. Select a work item with fulfilled dependencies and explicit acceptance criteria.
2. Record its design decision, threat/data impact and intended module repository.
3. Implement a bounded slice using synthetic fixtures and narrow provider interfaces.
4. Run relevant unit, contract, tenant-isolation, integration and workflow tests.
5. Record evidence, unresolved failures and the smallest next step in the checkpoint.
6. Prepare a reviewable change and release candidate; production release uses the deployment policy and required approvals.

Avoid auto-merging an agent's own code based solely on its own tests. Independent review, deterministic security checks and protected release identities remain part of an automated engineering organization. The current repository contains runnable local checks and a CI definition, not an unattended development-agent service.

## Domain discovery that must precede production features

Jurisdictions and legal entities; staffing-agency versus direct-employer workflows; customer billing and accounting basis; record retention/legal holds; union and public-sector rules; benefits/payroll providers; SSO requirements; data residency; accessibility and language requirements; expected scale; customer deployment tier; risk ownership; trained human review roles. These are tracked requirements rather than questions blocking the current foundation work.
