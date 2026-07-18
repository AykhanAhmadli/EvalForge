# Performance Benchmarks

The benchmark runner requires a live PostgreSQL/API stack and records only measurements returned
by that run. It does not contain baseline numbers or placeholder claims. Start the local fake
provider stack first:

```bash
npm run dev:detached
python benchmarks/run_benchmark.py \
  --database-url "$DATABASE_URL" \
  --api-url http://localhost:8000 \
  --dataset-size 100 \
  --scheduled-runs 20 \
  --queue-jobs 200 \
  --workers 4 \
  --api-samples 100 \
  --write-doc
```

The script seeds a uniquely named dataset, prompt, fake model configuration, and workspace. It
measures API scheduling requests, direct PostgreSQL queue claim/complete throughput across multiple
worker processes, and readiness endpoint latency without invoking an external provider. Output
includes throughput, median, p95, p99, failure rate, parameters, and hardware details. The
`--write-doc` flag writes `docs/benchmark-results.md` only after all requested measurements have
completed successfully.

Benchmark results are environment-specific. Do not compare them across machines, database
configurations, or code revisions without recording those differences.
