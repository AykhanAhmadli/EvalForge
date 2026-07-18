# EvalForge

EvalForge is a small control plane for running repeatable LLM evaluations. The intended workflow is straightforward: keep datasets and prompt/model configurations versioned, run the same checks after a change, compare the result with a baseline, and let CI decide whether the change is acceptable.

The repository includes the management and execution foundations: immutable dataset and prompt versions, safe model configurations, PostgreSQL-backed evaluation jobs, incremental results, documented metrics, cancellation, retries, and aggregate snapshots. Baselines and CI comparison are the next product layer.

## Why this shape

PostgreSQL is both the system of record and the job queue. That keeps run state, job state, and evaluation artifacts in one transaction boundary while the product is still small. Providers are hidden behind an adapter interface, so local development and tests use a deterministic fake provider without credentials or network calls.

There is no Redis, Celery, Kafka, or service mesh in the repository. Those would be reasonable changes only if measured queue throughput, latency, or isolation requirements made PostgreSQL insufficient.

## Stack

- React, TypeScript, Vite, Material UI, and TanStack Query
- FastAPI, SQLAlchemy, Alembic, and Python
- PostgreSQL 16
- A separate Python worker using a PostgreSQL-backed queue
- pytest, Vitest, and Playwright
- Docker Compose for local services

## Repository layout

```text
frontend/  Web application and browser tests
backend/   API, domain model, migrations, metrics, and provider adapters
worker/    Queue polling and job execution process
cli/       Command-line entrypoint for health checks and CI gates
tests/     Backend test suite
docs/      Architecture, lifecycle, metrics, and development notes
infra/     Docker Compose and container definitions
```

## Run locally

Requirements: Docker Desktop, Node.js 20+, npm, and Python 3.11+.

```bash
cp .env.example .env
npm run setup
npm run dev
```

The local services are available at:

- Web app: http://localhost:5173
- API: http://localhost:8000
- API documentation: http://localhost:8000/docs
- PostgreSQL: `localhost:5432`

To run the stack in the background:

```bash
npm run dev:detached
npm run logs
npm run down
```

## Checks

`npm run validate` runs Ruff, mypy, pytest, ESLint, Prettier, TypeScript, and Vitest. Playwright is kept separate because it needs a running frontend:

```bash
npm run validate
npm run test:e2e
```

The API exposes health and metadata endpoints plus workspace, suite, dataset, prompt, model-configuration, pricing, and evaluation-run management. Dataset uploads accept CSV and JSONL, versions are immutable, and the API supports preview/export, prompt-variable validation, asynchronous execution, cancellation, and result aggregation. The data model and API boundaries are documented in [docs/architecture.md](docs/architecture.md). See [docs/evaluation-lifecycle.md](docs/evaluation-lifecycle.md) for worker behavior and [docs/development.md](docs/development.md) for local workflow details.

## Project rules

The repository rules in [AGENTS.md](AGENTS.md) apply to code, tests, fixtures, and documentation. In particular, results must come from stored evaluation artifacts, provider access must go through adapters, and credentials must stay out of logs and source control.
