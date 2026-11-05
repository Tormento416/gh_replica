# Local development and automation

The current deliverable is a reference platform kernel and toolchain, not a production HRIS. Use synthetic data only. Python 3.12 and uv 0.13.4 were used for local verification. CI also declares Python 3.13, which is not yet locally verified.

From the `gh_replica` checkout:

```sh
make setup
make check
make demo
make compose
make serve
```

`make setup` installs the exact dependency graph from `uv.lock`. `make check` runs the security, contracts, approvals, idempotency, composition, restart, and loopback HTTP tests, validates the module catalog, and checks whitespace. `make demo` runs synthetic read and approval-controlled operations through the platform and module agents.

`make serve` starts a loopback-only diagnostic service with readiness and installed-module metadata. It has no tenant action endpoints, authentication integration, or production traffic support. Stop it with Ctrl+C. A live process is not retained across environment publication.

`make compose` creates `.local/composition`, a metadata-only composition of CRM and recruiting. Existing output directories are rejected instead of overwritten. Choose a new output path for additional compositions:

```sh
uv run --frozen hyrlink compose --modules core-hr,benefits --output .local/hr-benefits
uv run --frozen hyrlink compose --modules recruiting --output .local/recruiting-only
```

An unselected module is absent from the generated metadata tree and in-process registry. Deployment image omission, signature verification, migration orchestration, and workload removal remain release prerequisites; they are not implemented by this command.

## Separate module repositories

Fourteen local Git repositories are located at `../platform-modules/gh-module-*`, relative to the backbone checkout. Their Git origins name the intended private `Hyrlink-dev` repositories; an origin URL does not establish a remote repository exists. Each has an unborn `main` branch with scaffold files, a proprietary notice, a manifest, an agent policy, and a scaffold consistency test. No domain behavior is implemented. Remote creation and publication are deferred to the next session at the user's request.

Generate a fresh set into an unused path:

```sh
uv run --frozen hyrlink scaffold --output ../platform-modules-next --git
```

The generator refuses an existing destination and never edits reference repositories. A repository-creation plan is available without writes:

```sh
uv run --frozen hyrlink repositories
```

The `--apply` option performs the previously authorized private repository creation when intentionally resumed. It uses `gh_replica_fg_pat` when available, without writing it to files. The current integration returned HTTP 403; creation remains unverified. It stops on permission failures and refuses an existing public repository rather than changing its visibility. Do not run with shell tracing or print environment values.

## Contract source of truth

The executable v1 contract is `MODULE_SCHEMA` in `src/hyrlink_platform/contracts.py`; `catalog/*/module.json` supplies the 14 concrete examples. Exact core version compatibility is deliberate for v0.1. Broader compatible-version ranges require explicit evolution and migration tests.

The earlier YAML files under `templates/module` describe the long-term design and are not the executable v1 contract. The CLI-generated JSON scaffolds are authoritative for the current reference runtime.

## Persistence and production limits

The kernel supports a file-backed SQLite store for development audit, approvals, and invocation replay. The demo uses memory. Hash chaining detects some record modifications but is not independently anchored, immutable, or resistant to a privileged operator rewriting the entire chain. It does not prove regulatory compliance.

The invocation store retains results locally to support replay. Do not store production PII there. A crashed or failed handler remains in a state requiring reconciliation and is not automatically retried. External exactly-once effects, multi-process locking, timeout enforcement, cancellation, durable workflow execution, transactional outbox delivery, field encryption, and production retention are not supplied by this reference implementation.

`Principal` objects must come from a trusted authentication adapter. This prototype constructs them in tests and the demo. It is not a public request-body identity format. Real OIDC/SAML, tenant-host binding, row-level database enforcement, and centralized policy are required before exposing business APIs.

## Offline dependency verification

An initial wheel install into a fresh offline environment failed because cached environment restoration did not provide the registry metadata needed for dependency resolution. The correction is to export the frozen requirements with hashes and explicitly collect the platform-specific wheels while online:

```sh
make offline-bundle
uv venv .local/offline-check-new
uv pip install --offline --no-index --find-links .local/wheelhouse --require-hashes --python .local/offline-check-new/bin/python --requirement .local/requirements.txt
uv pip install --offline --no-index --no-deps --python .local/offline-check-new/bin/python dist/hyrlink_platform-0.1.0-py3-none-any.whl
.local/offline-check-new/bin/python -I -c 'from hyrlink_platform.runtime import Kernel; print("kernel wheel imported")'
```

This sequence was verified with `.local/wheel-check` on Linux x86_64 / Python 3.12. The wheelhouse is platform-specific; collect matching wheels for other targets. This proves offline installation of the reference kernel dependencies and package, not an air-gapped enterprise application, OS, GPU stack, identity provider, or complete build toolchain. The operator CLI still requires a source checkout (or an explicit `--root`) for its catalog and architecture manifest.

`make evidence` refreshes the local test evidence, including scaffold checks under `../platform-modules`. In another workspace use `hyrlink verify --output <path>` with an appropriate `--module-root`, or omit that optional argument when module scaffolds have not been generated.

## Windows workspace

The intended local layout is `D:\HRIS_project\gh_replica` alongside `D:\HRIS_project\platform-modules`. Operational paths are relative to the checkout or derived from the running Python interpreter. No cloud mount is required. Recreate virtual environments on Windows; do not move a Linux `.venv` across operating systems.

With Git, Python 3.12 and uv installed, use PowerShell:

```powershell
Set-Location 'D:\HRIS_project\gh_replica'
uv sync --frozen
uv run --frozen python scripts/dev.py check
uv run --frozen python scripts/dev.py demo
uv run --frozen python scripts/dev.py evidence
```

The Python development runner replaces Make on machines where Make is unavailable. Windows execution remains unverified until these commands run on the target machine. Existing Linux verification evidence is preserved as historical evidence, not a claim of Windows validation.

## Session continuation

Start with `docs/reports/FOUNDATION_REVIEW.md` and `docs/CONTINUATION.md`. Do not regenerate existing scaffolds or overwrite prior changes. This environment already isolates tasks; do not create worktrees unless the user asks. No supported scheduler was available to restart the agent after a session limit.
