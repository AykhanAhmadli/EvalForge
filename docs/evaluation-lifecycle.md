# Evaluation Lifecycle

This document expands the lifecycle defined in `docs/architecture.md`.

## Statuses

| Status | Meaning |
| --- | --- |
| `draft` | A run configuration exists but has not been queued. |
| `queued` | The API accepted the run and inserted a job. |
| `provisioning` | A worker claimed the job and is preparing row-level items. |
| `running` | Prompts are being rendered and provider calls are being executed. |
| `scoring` | Outputs are stored and metrics are being computed. |
| `completed` | All required outputs and metric results are stored. |
| `failed` | The run stopped due to an unrecoverable validation, provider, or infrastructure error. |
| `canceled` | A user or automation canceled the run before completion. |

## CI Gate Semantics

A CI gate compares a candidate run against a baseline run. The gate may fail only when:

- Both runs completed.
- The compared metrics have documented semantics.
- The threshold policy is stored with the comparison request.
- The regression decision can be reproduced from stored metric results.

If a candidate run is missing, still running, failed, or canceled, the CLI must report that state directly instead of inventing results.
