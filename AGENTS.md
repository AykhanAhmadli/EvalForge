# EvalForge Working Agreements

These rules apply to application code, tests, fixtures, and documentation. They are kept in a separate file so contributors and automation use the same standards.

- Never fabricate evaluation or benchmark results.
- External model providers must be accessed through adapters.
- Tests must use a deterministic fake provider by default.
- API keys must never be logged or committed.
- Every metric must have documented semantics.
- Run formatting, linting, type checks, and tests before completion.

Operational notes:

- Prefer deterministic fixtures over live model calls in tests.
- Treat evaluation artifacts as provenance-bearing records. Preserve dataset version, prompt version, model configuration, metric definitions, and run metadata.
- Keep secrets in local environment files or secret managers only. Do not add real keys to `.env`, logs, fixtures, snapshots, or documentation examples.
- New metrics must be added to `docs/metrics.md` and exposed through the API before they can be used in runs.
