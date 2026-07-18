# Management API

The live OpenAPI document is available at `/openapi.json`, with the interactive reference at `/docs` when the API is running.

## Workspaces and Suites

Workspace CRUD is available at `/api/v1/workspaces`. Evaluation suites are scoped to a workspace at `/api/v1/workspaces/{workspace_id}/suites`.

## Datasets

- `POST /api/v1/workspaces/{workspace_id}/datasets`: create dataset metadata.
- `GET|PATCH|DELETE /api/v1/datasets/{dataset_id}`: manage dataset metadata.
- `POST /api/v1/datasets/{dataset_id}/versions`: create an immutable version from JSON test cases.
- `POST /api/v1/datasets/{dataset_id}/versions/upload`: upload CSV or JSONL.
- `GET /api/v1/datasets/{dataset_id}/versions`: list versions.
- `GET /api/v1/dataset-versions/{version_id}/preview`: inspect a bounded preview.
- `GET /api/v1/dataset-versions/{version_id}/export`: download JSONL.

Every row must contain `input` and `expected_output`. CSV rows are numbered from 2 because row 1 is the header. JSONL rows are numbered from 1. Invalid uploads return `422` with an `errors` array containing `row_number`, `field`, and `message`.

Dataset versions do not have update or delete endpoints. A changed dataset creates the next version and leaves prior test cases unchanged.

## Prompts

- `POST /api/v1/workspaces/{workspace_id}/prompt-templates`: create a named template and version 1.
- `GET|PATCH|DELETE /api/v1/prompt-templates/{template_id}`: manage template metadata.
- `POST /api/v1/prompt-templates/{template_id}/versions`: append a new immutable version.
- `GET /api/v1/prompt-templates/{template_id}/compare`: compare two versions with a unified diff.
- `POST /api/v1/prompt-versions/{version_id}/validate`: check variables against a dataset version.

Variables use the form `{{ question }}`. Nested paths such as `{{ customer.name }}` are supported for object-valued `input` fields.

## Model Configurations

Model configuration CRUD is scoped to a workspace at `/api/v1/workspaces/{workspace_id}/model-configurations`, with individual resources at `/api/v1/model-configurations/{configuration_id}`. Supported built-in adapters are `fake` and `openai`.

The fake adapter is deterministic and requires no secret. The OpenAI adapter reads `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` from the environment. Credentials are rejected from request parameters and are never included in responses.
