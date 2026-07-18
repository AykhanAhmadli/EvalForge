from __future__ import annotations

from benchmarks.run_benchmark import summarize_latencies


def test_benchmark_throughput_uses_wall_clock_elapsed_time() -> None:
    result = summarize_latencies([10.0, 20.0], failures=1, total=3, elapsed_seconds=0.5)

    assert result["throughput_per_second"] == 6.0
    assert result["failure_rate"] == 1 / 3
