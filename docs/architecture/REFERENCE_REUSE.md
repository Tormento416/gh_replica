# Hyrlink reference assessment

This assessment is based on source inspection, not a complete security audit or execution of the existing products. Every reference checkout was left unchanged. No source code was copied into the new kernel. The implementation uses independently written contracts and security patterns informed by these references.

| Reference and inspected revision | Evidence inspected | Reuse candidates | Required work before adoption |
| --- | --- | --- | --- |
| `HyrLink-pro` / `9a9de4a594014f5e451f46f43f191dabbb3b06f4` | README, `slm_core/agent_templates.py`, tenant-isolation tests | Candidate/enterprise/internal realm boundaries; tenant-host binding; resume extraction and privacy patterns; constrained prompt templates | Confirm license/rights, review full implementations and deployed paths, replace permissive output parsing with schemas, contract-wrap domain behavior |
| `hyrlink` / `c300d71d331d1258d034b2a83d2fef843daaf719` | README, package manifest | React/TanStack design patterns, server-side provider connector, Radix UI components | UI/accessibility review; decide TanStack versus Next from real product needs; avoid importing Lovable-specific infrastructure or production credentials |
| `HyrLink-MCP` / `33ffddaea4151ee9bb03335c1b559517abe2b3b3` | README, Go manifest, source inventory | Fixed connector configuration and platform health integration | README explicitly states this is a first-pass health connector; enterprise API service auth is not implemented upstream; do not represent it as a complete integration |
| `hyrlink-pro-mcp` / `17cfd15a54b16ab6a855fe564679b837118e232d` | README, `internal/core/dispatcher.go`, architecture notes | Allowlisted action registry, strict auth boundary, input/output gates, bounded concurrency, body-free logs | Full source/license review, tenant binding, scoped service tokens, current Go toolchain verification, connector sandbox tests; partner calls are not enabled |
| `hyrlinkpro-coursework-devtesting` / `305de484f69a36b473b8d70623d5c9dba592edc1` | README, `slm_core/tenant_fairness.py`, agent template tests | Tenant-aware GPU admission, cancellation recovery, adversarial prompt fixtures | Cryptographically bind tenant identity instead of trusting a header; fairness/load tests; compare against main branch before selecting any experiment |

No top-level license file was found through the tracked-path inventory for these five references. That observation is not a conclusion about ownership; it means copying must wait for an explicit rights/provenance decision. Preserve notices for any third-party dependencies that are later adopted.

The removed `AI_resume_chatbot_template` checkout is outside the current selected reference set and was not used.

## Interpretation cautions

Prompt fences help models distinguish external text from instructions but do not guarantee injection resistance. Authorization, fixed tool allowlists and data boundaries remain outside the model. A health check connector does not establish full provider integration. A file overwrite does not guarantee physical erasure on SSD or copy-on-write storage. A local append-only or hash-linked log does not create a compliance-grade immutable audit service.
