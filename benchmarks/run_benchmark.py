from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import platform
import statistics
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from queue import Empty
from typing import Any
from uuid import uuid4


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = int((percentile_value / 100) * len(ordered) + 0.999999) - 1
    index = max(0, min(len(ordered) - 1, rank))
    return ordered[index]


def summarize_latencies(values: list[float], *, failures: int, total: int) -> dict[str, Any]:
    return {
        "count": total,
        "successes": len(values),
        "failures": failures,
        "failure_rate": failures / total if total else 0.0,
        "throughput_per_second": total / (sum(values) / 1000) if values and sum(values) else 0.0,
        "latency_ms": {
            "median": statistics.median(values) if values else None,
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
        },
    }


def queue_worker(worker_id: str, result_queue: Any) -> None:
    from evalforge.db import get_session_factory
    from evalforge.queue import claim_next_job, complete_job

    processed = 0
    failures = 0
    claim_latencies: list[float] = []
    factory = get_session_factory()
    while True:
        try:
            with factory() as session:
                started = time.perf_counter()
                job = claim_next_job(session, worker_id=worker_id, lease_seconds=60)
                claim_latencies.append((time.perf_counter() - started) * 1000)
                if job is None:
                    break
                complete_job(session, job)
                processed += 1
        except Exception:
            failures += 1
    result_queue.put(
        {"processed": processed, "failures": failures, "claim_latencies": claim_latencies}
    )


def seed_fixture(dataset_size: int) -> dict[str, str]:
    from evalforge.db import get_session_factory
    from evalforge.models import (
        Dataset,
        DatasetVersion,
        EvaluationSuite,
        ModelConfiguration,
        PromptTemplate,
        PromptVersion,
        TestCase,
        Workspace,
    )

    workspace = Workspace(name="Benchmark Workspace", slug=f"benchmark-{uuid4().hex[:12]}")
    dataset = Dataset(
        workspace_id=workspace.id,
        name="Benchmark Dataset",
        slug=f"benchmark-dataset-{uuid4().hex[:8]}",
        tags=["benchmark"],
    )
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        source_format="manual",
        row_count=dataset_size,
        schema_fields=["question", "expected_output", "tags"],
        content_hash=uuid4().hex,
        created_by="benchmark",
    )
    prompt = PromptTemplate(
        workspace_id=workspace.id,
        name="Benchmark Prompt",
        slug=f"benchmark-prompt-{uuid4().hex[:8]}",
        tags=["benchmark"],
    )
    prompt_version = PromptVersion(
        prompt_template_id=prompt.id,
        version_number=1,
        template="Answer {{ question }}",
        variables=["question"],
        created_by="benchmark",
    )
    model = ModelConfiguration(
        workspace_id=workspace.id,
        name="Benchmark Fake",
        slug=f"benchmark-fake-{uuid4().hex[:8]}",
        provider="fake",
        model_name="evalforge-fake-v1",
        temperature=Decimal("0"),
        max_tokens=32,
        timeout_seconds=30,
        parameters={},
    )
    suite = EvaluationSuite(
        workspace_id=workspace.id,
        name="Benchmark Suite",
        slug=f"benchmark-suite-{uuid4().hex[:8]}",
        dataset_version_id=version.id,
        prompt_version_id=prompt_version.id,
        model_configuration_id=model.id,
        metric_names=["exact_match"],
        metric_options={},
    )
    cases = [
        TestCase(
            dataset_version_id=version.id,
            row_number=index,
            input={"question": f"benchmark question {index}"},
            expected_output=f"benchmark answer {index}",
            row_metadata={},
            tags=["benchmark"],
        )
        for index in range(1, dataset_size + 1)
    ]
    factory = get_session_factory()
    with factory() as session:
        session.add_all([workspace, dataset, version, prompt, prompt_version, model, suite, *cases])
        session.commit()
    return {"workspace_id": str(workspace.id), "suite_id": str(suite.id)}


def measure_api(api_url: str, workspace_id: str, suite_id: str, samples: int) -> dict[str, Any]:
    import httpx

    headers = {"X-EvalForge-Workspace-ID": workspace_id}
    api_key = os.getenv("EVALFORGE_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    latencies: list[float] = []
    failures = 0
    with httpx.Client(base_url=api_url.rstrip("/"), headers=headers, timeout=15.0) as client:
        for _ in range(samples):
            started = time.perf_counter()
            try:
                response = client.get("/health/ready")
            except httpx.HTTPError:
                failures += 1
            else:
                elapsed = (time.perf_counter() - started) * 1000
                if response.is_success:
                    latencies.append(elapsed)
                else:
                    failures += 1
    total_seconds = sum(latencies) / 1000 if latencies else 0.0
    result = summarize_latencies(latencies, failures=failures, total=samples)
    result["throughput_per_second"] = samples / total_seconds if total_seconds else 0.0
    return result


def measure_scheduling(
    api_url: str, workspace_id: str, suite_id: str, count: int
) -> dict[str, Any]:
    import httpx

    headers = {"X-EvalForge-Workspace-ID": workspace_id}
    api_key = os.getenv("EVALFORGE_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    latencies: list[float] = []
    failures = 0
    with httpx.Client(base_url=api_url.rstrip("/"), headers=headers, timeout=15.0) as client:
        for _ in range(count):
            started = time.perf_counter()
            try:
                response = client.post(
                    f"/api/v1/workspaces/{workspace_id}/suites/{suite_id}/runs", json={}
                )
            except httpx.HTTPError:
                failures += 1
            else:
                elapsed = (time.perf_counter() - started) * 1000
                if response.status_code == 201:
                    latencies.append(elapsed)
                else:
                    failures += 1
    result = summarize_latencies(latencies, failures=failures, total=count)
    elapsed_seconds = sum(latencies) / 1000 if latencies else 0.0
    result["throughput_per_second"] = count / elapsed_seconds if elapsed_seconds else 0.0
    return result


def measure_queue(job_count: int, worker_count: int) -> dict[str, Any]:
    from evalforge.db import get_session_factory
    from evalforge.models import Job

    factory = get_session_factory()
    with factory() as session:
        jobs = [Job(kind="benchmark.noop", payload={"benchmark": True}) for _ in range(job_count)]
        session.add_all(jobs)
        session.commit()

    context = mp.get_context("spawn")
    result_queue = context.Queue()
    started = time.perf_counter()
    processes = [
        context.Process(target=queue_worker, args=(f"benchmark-worker-{index}", result_queue))
        for index in range(worker_count)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
    elapsed_seconds = time.perf_counter() - started
    processed = 0
    failures = 0
    latencies: list[float] = []
    for _ in processes:
        try:
            result = result_queue.get(timeout=5)
        except Empty:
            failures += 1
            continue
        processed += result["processed"]
        failures += result["failures"]
        latencies.extend(result["claim_latencies"])
    return {
        "count": job_count,
        "processed": processed,
        "workers": worker_count,
        "failures": failures + (job_count - processed),
        "failure_rate": (failures + (job_count - processed)) / job_count if job_count else 0.0,
        "throughput_per_second": processed / elapsed_seconds if elapsed_seconds else 0.0,
        "latency_ms": {
            "median": statistics.median(latencies) if latencies else None,
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
        },
        "elapsed_seconds": elapsed_seconds,
    }


def markdown_report(results: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Results",
        "",
        f"Generated at: `{results['generated_at']}`",
        "",
        "These measurements were captured by `benchmarks/run_benchmark.py`; they are "
        "environment-specific.",
        "",
        "## Parameters",
        "",
        "```json",
        json.dumps(results["parameters"], indent=2, sort_keys=True),
        "```",
        "",
        "## Hardware",
        "",
        "```json",
        json.dumps(results["hardware"], indent=2, sort_keys=True),
        "```",
        "",
        "## Measurements",
        "",
        "| Measurement | Throughput/s | Median ms | p95 ms | p99 ms | Failure rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, measurement in results["measurements"].items():
        latency = measurement.get("latency_ms", {})
        lines.append(
            f"| {name} | {measurement.get('throughput_per_second')} | "
            f"{latency.get('median')} | {latency.get('p95')} | {latency.get('p99')} | "
            f"{measurement.get('failure_rate')} |"
        )
    lines.extend(["", "External model provider latency is not included in these measurements.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure EvalForge API and PostgreSQL queue performance."
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--dataset-size", type=int, default=100)
    parser.add_argument("--scheduled-runs", type=int, default=20)
    parser.add_argument("--queue-jobs", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--api-samples", type=int, default=100)
    parser.add_argument("--write-doc", action="store_true")
    args = parser.parse_args()
    counts = (
        args.dataset_size,
        args.scheduled_runs,
        args.queue_jobs,
        args.workers,
        args.api_samples,
    )
    if not args.database_url or min(counts) < 1:
        parser.error(
            "database URL and all benchmark counts must be configured with positive values"
        )
    os.environ["DATABASE_URL"] = args.database_url

    fixture = seed_fixture(args.dataset_size)
    measurements = {
        "api_readiness": measure_api(
            args.api_url, fixture["workspace_id"], fixture["suite_id"], args.api_samples
        ),
        "evaluation_scheduling": measure_scheduling(
            args.api_url, fixture["workspace_id"], fixture["suite_id"], args.scheduled_runs
        ),
        "postgres_queue_multi_worker": measure_queue(args.queue_jobs, args.workers),
    }
    results = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "parameters": vars(args) | {"fixture_workspace_id": fixture["workspace_id"]},
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "measurements": measurements,
    }
    if args.write_doc:
        Path("docs/benchmark-results.md").write_text(markdown_report(results), encoding="utf-8")
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
