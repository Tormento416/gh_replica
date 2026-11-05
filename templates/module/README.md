# Installable Module Template

The YAML files here preserve the earlier target-design sketch. Use `uv run --frozen hyrlink scaffold --output <unused-directory> --git` for executable v0.1 JSON manifests, agent policies, local repositories and scaffold tests. The canonical current schema lives in `src/hyrlink_platform/contracts.py`.

Use this template to initialize a module repository. A module owns one bounded business domain and is independently buildable, testable, versioned, installable, upgradeable, and removable.

## Required Layout

```text
module.yaml                 Module identity, compatibility, dependencies, and capabilities
agent/agent.yaml            Agent identity, intents, tools, policies, and approval classes
contracts/                  OpenAPI, AsyncAPI, JSON Schema, and workflow contracts
src/                        Domain application and workers
migrations/                 Module-owned database migrations
deploy/                     Module images and deployment descriptors
tests/                      Unit, contract, integration, migration, and uninstall tests
docs/                       Domain model, operations, data retention, and runbooks
SECURITY.md                 Threat model and security contact
LICENSE                     Module license
```

Replace every `example` value in the template files. A module cannot be released until core compatibility, clean installation, upgrade, rollback, removal, tenant isolation, authorization, audit, and agent-tool tests pass.
