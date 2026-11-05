# gh_replica

Development status: reference kernel and module scaffolding. Start with the [foundation review report](docs/reports/FOUNDATION_REVIEW.md), [local development guide](docs/DEVELOPMENT.md), and [implementation roadmap](docs/architecture/REQUIREMENTS_AND_ROADMAP.md). The backbone may be public; product modules remain private under `Hyrlink-dev`.

The platform is an AI-native business and workforce operations suite combining the recruiting depth of Greenhouse with the customer and workflow capabilities of Salesforce. It connects client relationships, talent acquisition, HR, benefits, payroll, finance, logistics, and employee services through one shared data and automation layer. Embedded AI agents complete routine work, coordinate processes, identify exceptions, and support decisions while preserving human approval for sensitive actions. The platform replaces fragmented tools and manual handoffs with transparent, measurable workflows spanning the entire client, candidate, and employee lifecycle. Its goal is to help smaller teams operate faster, more accurately, and at significantly greater scale.

## Platform Suite

- **Client CRM:** Manages prospects, customers, contacts, contracts, service plans, and ongoing relationships with AI-guided follow-ups and account intelligence.

- **Recruiting and ATS:** Runs requisitions, job publishing, sourcing, applications, interviews, scorecards, offers, and hiring workflows. [Hyrlink Pro](https://github.com/hyrlink-dev/hyrlink-pro) will serve as a foundation for this module, with compatible recruiting services reused and extended across the suite.

- **Candidate and Anti-ATS Experience:** Gives candidates transparent status, reusable profiles, skills-based matching, and a more accessible, human-centered application experience. Hyrlink Pro capabilities will be incorporated here to accelerate delivery and share candidate, job, application, and matching services with recruiting workflows.

- **Core HRIS:** Maintains the authoritative employee record, organizational structure, job history, compensation, policies, documents, and lifecycle changes.

- **Onboarding and Offboarding:** Coordinates documents, screening, account access, equipment, training, payroll readiness, and departures through automated workflows.

- **Benefits Administration:** Manages eligibility, enrollment, dependents, life events, plan communications, carrier feeds, and discrepancy resolution.

- **Payroll, Time, and Leave:** Handles earnings, deductions, taxes, timekeeping, leave, payroll validation, reconciliation, and exception management.

- **Accounts Payable and Vendors:** Automates vendor onboarding, invoice capture, matching, approvals, payment preparation, duplicate detection, and spend controls.

- **Assets and Logistics:** Tracks equipment, inventory, purchasing, assignments, shipments, returns, and recovery across the employee lifecycle.

- **Financial Management:** Supports billing, budgets, allocations, ledger activity, reconciliation, forecasting, and workforce cost analysis.

- **Cases and Incident Management:** Provides secure intake, investigation workflows, evidence management, accommodations, corrective actions, deadlines, and reporting.

- **Workflow Automation:** Connects every system through configurable tasks, approvals, SLAs, escalations, rules, and exception queues.

- **AI Agent Platform:** Supplies specialized agents that interpret documents, retrieve policy knowledge, recommend actions, execute approved work, and learn from operational outcomes.

- **Analytics and Process Intelligence:** Measures performance, cost, accuracy, workload, compliance, fairness, and automation while identifying process bottlenecks.

- **Communications and Employee Service:** Unifies email, SMS, notifications, self-service requests, knowledge assistance, and personalized employee support.

- **Integration Hub:** Synchronizes identity, payroll, benefits, finance, background screening, job boards, communications, and other external providers.

- **Administration, Security, and Compliance:** Controls organizations, permissions, policies, consent, audit history, data retention, integrations, and regulatory requirements.

## Shared Platform Direction

The suite will use a common identity, organization, workflow, audit, communications, analytics, and AI foundation across every module. Recruiting and Anti-ATS capabilities from Hyrlink Pro will be assessed at the service and data-contract level so reusable components can be integrated without duplicating functionality or tightly coupling the broader HRIS platform to one module.

The foundational architecture, repository boundaries, module installation model, and agent responsibilities are defined in [Platform Foundation](docs/architecture/PLATFORM_FOUNDATION.md). New modules begin from the [module template](templates/module/README.md).

## Repository Ownership

`gh_replica` is the canonical backbone repository and source of truth for platform architecture, shared contracts, the core runtime, module compatibility, release composition, and deployment configuration. Each optional product module has its own repository and owns only its domain code, module agent, migrations, contracts, tests, and deployable artifacts. The additional source repositories currently mounted in the development environment are read-only references that may be scanned for useful tools, code, scripts, patterns, or services. Any selected component must be reviewed for compatibility, security, licensing, and maintainability before it is adapted into the backbone or the appropriate module repository.

## Run the Foundation

```sh
make setup
make check
make demo
```

Python 3.12 and uv are required. The demo uses synthetic data and deterministic agent routing, with no AI-provider credential or GPU required. It demonstrates installed-module boundaries, tenant/permission checks, server-issued approvals, replay handling, and local audit integrity. Module business logic, production identity, signed artifact installation and autonomous model planning remain roadmap work.
