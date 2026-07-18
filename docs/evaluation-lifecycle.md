# Evaluation Lifecycle

## Run States

| Status | Meaning |
| --- | --- |
| `queued` | The API stored a run and its PostgreSQL job. |
| `running` | A worker is rendering prompts and calling the provider adapter. |
| `completed` | Every test case completed successfully. |
| `partially_failed` | At least one test case completed and at least one had a permanent failure. |
| `failed` | The run could not produce any successful case, or setup failed. |
| `cancelled` | Cancellation was requested and the worker stopped before completion. |

The API also accepts legacy `draft`, `provisioning`, `scoring`, and `canceled` vocabulary in
the status model for compatibility with the initial scaffold. New runs use the states above.

## Job Processing

1. `POST /api/v1/workspaces/{workspace_id}/evaluation-runs` validates workspace ownership and
   prompt variables, inserts the run, and inserts one `evaluation.run` job in the same database
   transaction.
2. A worker claims one due job with `FOR UPDATE SKIP LOCKED`. The claim records the worker,
   attempt count, and a lease expiry. A second worker cannot claim that row while the lease is
   active.
3. The worker stores a row-level result before calling the provider, then commits the output,
   latency, token usage, errors, and metric results before moving to the next test case.
4. A crashed worker leaves a lease. Once it expires, another worker may reclaim the job.
5. Only `TransientProviderError` is retried. Permanent provider errors, invalid prompts, and
   configuration errors are stored as failures and are not retried.
6. Cancellation is cooperative. Queued jobs are cancelled immediately; running jobs observe
   `cancel_requested_at` between test cases and finish with `cancelled`.

## Reproducibility

The fake provider derives its output from a configured seed, model name, and rendered prompt.
Tests and local demonstrations use it by default. External providers are adapter-only and are
never called directly by the API or metrics code.
