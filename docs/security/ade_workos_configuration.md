# WorkOS configuration

WorkOS is the selected identity provider for the HRIS backbone. The user has confirmed that this platform uses a different WorkOS organization or environment from the existing Hyrlink endpoint. Provision and configure its own client ID, issuer, signing keys, API credentials, callbacks and organization mappings; do not copy or assume the existing deployment's values. Enter secret values in the environment's secure settings or a deployment secret manager. Do not put values in this file, the repository, chat, branch names, logs, or screenshots.

## Configuration inventory

| Name | Classification | Purpose | Status |
| --- | --- | --- | --- |
| `WORKOS_CLIENT_ID` | Non-secret identifier | Identifies the WorkOS environment and AuthKit session signing-key set. | Needed to retrieve session signing keys. |
| `WORKOS_ISSUER` | Non-secret URL | Exact trusted issuer for the chosen WorkOS token profile. Use the issuer configured for that environment. | Needed before token validation can be configured. |
| `WORKOS_AUDIENCE` | Non-secret identifier | Exact intended audience for this platform API. Use the value actually issued for the selected token profile. | Needed before token validation can be configured. |
| `WORKOS_API_KEY` | Secret | Server-side WorkOS API calls such as authentication and membership administration. Never expose it to browsers. | Needed when the login or membership API integration is implemented; not needed to verify a signed token locally. |
| `WORKOS_COOKIE_PASSWORD` | Secret | Session sealing if the WorkOS sealed-session flow is adopted. | Conditional; not used by the current token-boundary prototype. |
| `WORKOS_REDIRECT_URI` | Non-secret URL | Registered callback for a specific application/environment. | Needed when interactive sign-in is implemented. |
| WorkOS organization ID | Non-secret identifier | Maps a customer organization to the platform's own tenant record. | Stored as tenant configuration; not a global secret. |

Use separate WorkOS development, staging, and production environments and keys. Grant the minimum API permissions the implemented features require. Configure callback URLs in the WorkOS dashboard for the intended deployment; do not guess a production callback.

## Local development file

From the backbone checkout in PowerShell, create the local file only if it does not already exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Fill in `WORKOS_CLIENT_ID` and `WORKOS_API_KEY` from the separate WorkOS development environment. Leave the other fields blank until their values are established. `.env` is ignored by Git; `.env.example` contains placeholders only. Keep `.env` on the server or development machine and never include it in an archive or browser bundle.

Check only whether values are present, without displaying them:

```powershell
uv run --env-file .env --frozen hyrlink workos-config
```

The command loads the file for that invocation and reports `set` or `not set`. It does not validate credentials, contact WorkOS, start sign-in, or automatically configure other processes. Existing process environment variables take precedence. For deployed services, inject values through the deployment's secret manager rather than distributing a local file.

## Current integration boundary

The backbone can validate an RS256 token using explicitly trusted RSA public keys, bind an organization claim to an active server-resolved tenant, and load permissions from a server-side grants source. `ade_workos_keys.py` provides a bounded, fixed-host client and short-lived key snapshot for the WorkOS AuthKit **session-token** JWKS endpoint. It does not send the API key to the JWKS endpoint. Expired snapshots are not reused on fetch failure; trusted operators can request an explicit refresh during key rotation. A request-supplied key ID must never trigger an unbounded refresh.

WorkOS has multiple token profiles. AuthKit Connect tokens can use a different issuer, audience, and JWKS endpoint from AuthKit session tokens. The generic verifier currently requires `aud`, `nbf`, and a configurable token-use claim. Do not assume those claims are present in a particular WorkOS profile; the profile and audience must be confirmed against WorkOS documentation and a controlled integration test. No live WorkOS login, key rotation, provider-specific claim mapping, production ingress, or persisted grants are wired yet.

The reference HTTP middleware connects the session-key snapshot to the identity boundary and injects the verified principal into `ade.principal`. It rejects duplicate host or authorization headers, ignores forwarded-host headers, and rejects WebSocket requests. It runs blocking verification and key retrieval in a worker thread; configured tenant and grant providers must therefore be thread-safe and bounded. The middleware is not attached to a production application. A trusted ingress must validate the externally addressed host and provide TLS, request-size limits, rate limiting, and timeout controls. Unknown signing keys do not trigger an immediate refresh; an authorized operator can refresh the key store explicitly during rotation.

Current reference documentation: [WorkOS sessions](https://workos.com/docs/user-management/sessions), [AuthKit Connect token claims](https://workos.com/docs/authkit/connect/token-claims), and [JWKS reference](https://workos.com/docs/reference/authkit/session-tokens/jwks). Treat provider documentation as the authority for the actual configured environment.

## When values are ready

Add values securely in the environment or secret manager, not here. Then the integration can test the configured profile with a test organization and non-production account. Do not share actual access tokens or API keys in the conversation. The current workspace reports no WorkOS runtime variables or secret bindings; no values have been tested.
