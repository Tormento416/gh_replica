# Repository Instructions

`gh_replica` is the canonical backbone and primary coordination repository for this platform.

- Make core runtime, shared contract, module registry, release composition, architecture, and platform deployment changes in this repository.
- Put module-specific application code, migrations, tests, deployable artifacts, and module agents in that module's repository after it is created.
- Treat the separately provided Hyrlink reference repositories as read-only sources for scanning and evaluating reusable tools, code, scripts, services, and architectural patterns. Resolve their locations from the active workspace; never assume a particular machine path.
- Do not modify, commit to, or publish changes from a reference repository unless the user explicitly requests work in that repository.
- Before adopting reference code, review its license, dependencies, security implications, data contracts, tests, and fit with the platform architecture.
- Copy or adapt only the required components into `gh_replica`, preserving attribution and license notices when required.
- Avoid creating worktrees during cloud environment tasks unless the user explicitly requests one.
- The backbone may be public. Product modules must remain private under `Hyrlink-dev` until the user changes that policy.
- Read `docs/CONTINUATION.md` and `docs/reports/FOUNDATION_REVIEW.md` before resuming foundation work. Preserve existing local modifications and do not regenerate into occupied output directories.
- Favor maintained NVIDIA libraries when benchmarks, licensing, security, offline operation and maintenance cost justify them; preserve provider-neutral platform interfaces.
- Keep optional module dependencies outside the backbone. Do not claim the reference kernel, metadata composer, synthetic handlers or local audit chain are production-ready.
- Record material decisions in `docs/architecture/DECISIONS.md`; use `make check` and the relevant module tests before marking a work item complete.
