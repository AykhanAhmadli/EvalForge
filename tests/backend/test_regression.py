from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from evalforge.models import RegressionRule
from evalforge.regression import CaseSample, MetricSample, RunSnapshot, evaluate_regression


def snapshot(
    run_id: str,
    *,
    status: str = "completed",
    failed_cases: int = 0,
    exact: str = "1",
    latency: tuple[str, ...] = ("10", "20"),
    cost: str = "0.02",
) -> RunSnapshot:
    samples = [
        MetricSample("exact_match", Decimal(exact), "valid", ("math",)),
        *(MetricSample("latency_ms", Decimal(value), "valid", ("math",)) for value in latency),
        MetricSample("estimated_cost", Decimal(cost), "valid", ("math",)),
    ]
    cases = tuple(
        [CaseSample("completed", ("math",)) for _ in range(max(0, 2 - failed_cases))]
        + [CaseSample("failed", ("math",)) for _ in range(failed_cases)]
    )
    return RunSnapshot(
        run_id=uuid4() if run_id == "" else uuid4(),
        status=status,
        failed_cases=failed_cases,
        metric_names=("exact_match", "latency_ms", "estimated_cost"),
        metric_samples=tuple(samples),
        cases=cases,
    )


def rule(
    rule_type: str, threshold: str, *, metric_name: str | None = None, tag: str | None = None
) -> RegressionRule:
    return RegressionRule(
        rule_type=rule_type,
        metric_name=metric_name,
        tag=tag,
        operator=(">=" if rule_type in {"minimum_overall_score", "per_metric_threshold"} else "<="),
        threshold=Decimal(threshold),
    )


def test_all_configured_rule_types_pass_and_respect_tags() -> None:
    baseline = snapshot("baseline", exact="0.9", latency=("10", "20"), cost="0.02")
    candidate = snapshot("candidate", exact="0.95", latency=("15", "25"), cost="0.03")
    evaluation = evaluate_regression(
        baseline,
        candidate,
        [
            rule("minimum_overall_score", "0.9", tag="math"),
            rule("maximum_score_decrease", "0.1", tag="math"),
            rule("maximum_failed_cases", "0", tag="math"),
            rule("maximum_p95_latency", "25", tag="math"),
            rule("maximum_estimated_cost", "0.04", tag="math"),
            rule("per_metric_threshold", "0.9", metric_name="exact_match", tag="math"),
        ],
    )
    assert evaluation.status == "passed"
    assert evaluation.regression_detected is False


def test_score_and_operational_threshold_failures_are_reported() -> None:
    baseline = snapshot("baseline", exact="1", latency=("10", "20"), cost="0.01")
    candidate = snapshot(
        "candidate", failed_cases=1, exact="0.4", latency=("10", "200"), cost="0.20"
    )
    evaluation = evaluate_regression(
        baseline,
        candidate,
        [
            rule("minimum_overall_score", "0.8"),
            rule("maximum_score_decrease", "0.1"),
            rule("maximum_failed_cases", "0"),
            rule("maximum_p95_latency", "100"),
            rule("maximum_estimated_cost", "0.10"),
            rule("per_metric_threshold", "0.8", metric_name="exact_match"),
        ],
    )
    assert evaluation.status == "failed"
    assert len(evaluation.violations) == 6


def test_cancelled_and_partial_runs_are_not_comparable() -> None:
    baseline = snapshot("baseline")
    cancelled = snapshot("cancelled", status="cancelled")
    partial = snapshot("partial", status="partially_failed", failed_cases=1)
    configured = [rule("maximum_failed_cases", "0")]

    assert evaluate_regression(baseline, cancelled, configured).status == "not_evaluable"
    assert evaluate_regression(baseline, partial, configured).status == "not_evaluable"
