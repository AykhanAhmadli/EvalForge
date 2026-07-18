# EvalForge CLI

The CLI is intended for local use and CI. It sends an `Authorization: Bearer` header using the
`EVALFORGE_API_KEY` environment variable; the key is never printed. The API URL, workspace, and
baseline can be supplied with `EVALFORGE_API_URL`, `EVALFORGE_WORKSPACE_ID`, and
`EVALFORGE_BASELINE_ID`.

Install it from the repository:

```bash
python -m pip install ./cli
```

Typical CI flow:

```bash
run_id="$(evalforge run "$EVALFORGE_SUITE_ID" --json | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
evalforge wait "$run_id"
evalforge compare "$run_id"
evalforge export "$run_id" --format json --output evaluation-results.json
```

Commands return zero only when the requested operation passes. `wait` returns non-zero for failed,
partially failed, cancelled, and timed-out runs. `compare` returns non-zero when a configured rule
fails or the comparison is not evaluable. An unreachable API returns exit code `3`. Use `--json`
on `run`, `wait`, `compare`, or `health` for one JSON object on stdout. Export writes stored result
records only and supports `--format json` or `--format csv`.

Suites must have dataset version, prompt version, model configuration, and optional metric settings
configured through the API before `evalforge run SUITE_ID` can queue them.
