# Development

## Local Setup

The local workflow assumes Docker Desktop, Node.js 20 or newer, npm, and Python 3.11 or newer.

```bash
cp .env.example .env
npm run setup
```

## Start The Stack

```bash
npm run dev
```

Docker Compose starts the following services:

- PostgreSQL
- Alembic migrations
- FastAPI API
- worker process
- Vite frontend

The migration container runs before the API and worker. The frontend waits for the API health check.

## Validate Changes

```bash
npm run validate
```

This runs:

- Ruff linting and formatting checks
- mypy for Python type checks
- pytest for backend tests
- ESLint and Prettier checks
- TypeScript checks
- Vitest unit tests

Playwright is available separately:

```bash
npm run test:e2e
```

## Database Migrations

Create migrations in `backend/alembic/versions`. Apply migrations locally with:

```bash
npm run db:migrate
```

Docker Compose runs migrations automatically before the API and worker start.
