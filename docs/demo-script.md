# Three-Minute Demo Script

This script uses the seeded deterministic fake provider. It demonstrates product behavior without
claiming a benchmark result.

## 0:00-0:30: Start

```bash
cp .env.example .env
npm run setup
npm run dev:detached
```

Open `http://localhost:5173` and point out that the workspace, API, worker, and database are
separate runtime processes while PostgreSQL remains the queue and system of record.

## 0:30-1:15: Inputs

Open Datasets and show the seeded `Starter Questions` version. Upload a small CSV and open the
preview. Switch to Prompts, select the seeded prompt, and create a second prompt version. The
version IDs, source format, and row numbers come from the API; no result is invented by the UI.

## 1:15-2:15: Run

Open Evaluation runs, choose the dataset version, prompt version, and deterministic fake model,
then queue a run. Show the queued/running status, progress, case results, latency, and token
usage. Explain that the worker persists each case incrementally and cancellation is cooperative.

## 2:15-3:00: Gate

Open Regression rules, save a completed run as a baseline, and add a threshold. The CLI equivalent
is:

```bash
run_id="$(evalforge run "$EVALFORGE_SUITE_ID" --json | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
evalforge wait "$run_id"
evalforge compare "$run_id"
```

Close by noting that a passing gate means only that this candidate stayed within configured bounds
for this dataset and configuration. See [regression-rules.md](regression-rules.md).
