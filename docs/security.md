# Security Notes

EvalForge is designed to make unsafe defaults visible. It is not an identity provider and should
be deployed behind an organization-managed secret store, TLS termination, and appropriate network
controls.

## Runtime Secrets

Provider credentials are read by provider adapters from runtime environment variables such as
`OPENAI_API_KEY`. They are rejected from model-configuration request bodies, never persisted in
the database, and are not returned by the API. EvalForge does not encrypt provider credentials
because it does not store them; production deployments should use a secret manager and inject
them only into the API/worker process that needs them.

API keys are also runtime configuration. Set `API_AUTH_REQUIRED=true`, provide comma-separated
`API_KEYS`, and assign each key to one or more workspaces with `API_KEY_WORKSPACES`:

```text
API_KEYS=runtime-key-from-a-secret-manager
API_KEY_WORKSPACES=runtime-key-from-a-secret-manager:workspace-uuid
```

Clients send `Authorization: Bearer <key>` and `X-EvalForge-Workspace-ID`. The API rejects keys
without a workspace assignment and applies the assignment to direct resource lookups as well as
workspace-scoped routes. Local development leaves authentication disabled by default so the fake
provider demo can start without credentials; do not use that setting for a shared deployment.
The frontend can forward a scoped API key through `VITE_API_KEY`, but browser-delivered keys are
visible to that browser; use a narrow workspace assignment or terminate authentication at a
trusted server-side proxy for public deployments.

## Input and Output Boundaries

- Request bodies default to a 10 MiB limit through `MAX_REQUEST_BYTES`.
- Dataset uploads default to a 10 MiB limit through `MAX_UPLOAD_BYTES`.
- Uploads must use `.csv`, `.jsonl`, or `.ndjson`, must be UTF-8, and are parsed with required-field,
  row-number, metadata, and tag validation before persistence.
- Model-generated text is stored as data and rendered as text in the React dashboard. The frontend
  does not inject model output as HTML.
- Provider and worker errors are reduced to safe categories before storage/logging; credentials and
  raw response bodies are not included.

## Prompt Injection Limitations

Prompt injection is an evaluation subject, not something EvalForge can automatically eliminate.
Dataset inputs and expected outputs may contain instructions that attempt to redirect a provider.
EvalForge currently renders the configured prompt and records the provider response; it does not
guarantee instruction hierarchy, tool isolation, data-loss prevention, or semantic safety. Treat
datasets and model outputs as untrusted, keep real secrets out of evaluation inputs, use isolated
provider credentials, and add task-specific metrics or human review for security-sensitive claims.

## Known Security Limitations

- API keys are bearer credentials with environment-based rotation; there is no user account, role,
  revocation, or audit-log service yet.
- TLS, secret-manager integration, database encryption at rest, backups, and network policy belong
  to the deployment environment.
- Metrics are imperfect proxies for quality and should not be the sole approval signal for high-risk
  decisions.
