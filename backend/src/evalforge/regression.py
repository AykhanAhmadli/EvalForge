"""Deterministic regression-rule evaluation over stored run artifacts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from evalforge.metrics import METRIC_BY_NAME
from evalforge.models import RegressionRule

QUALITY_METRICS = {
    name
    for name, definition in METRIC_BY_NAME.items()
    if definition.direction == "higher_is_better"
}


@dataclass(frozen=True)
class MetricSample:
    metric_name: str
    value: Decimal
    status: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class CaseSample:
    status: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class RunSnapshot:
    run_id: UUID
    status: str
    failed_cases: int
    metric_names: tuple[str, ...]
    metric_samples: tuple[MetricSample, ...]
    cases: tuple[CaseSample, ...]


@dataclass(frozen=True)
class RegressionViolation:
    rule_id: UUID | None
    rule_type: str | None
    metric_name: str | None
    tag: str | None
    baseline_value: Decimal | None
    candidate_value: Decimal | None
    threshold: Decimal | None
    message: str


@dataclass(frozen=True)
class RegressionEvaluation:
    status: str
    regression_detected: bool
    violations: tuple[RegressionViolation, ...]
    evaluated_at: datetime


def _tagged(values: Sequence[MetricSample], tag: str | None) -> list[MetricSample]:
    if tag is None:
        return list(values)
    return [value for value in values if tag in value.tags]


def _valid_metric_values(snapshot: RunSnapshot, metric_name: str, tag: str | None) -> list[Decimal]:
    return [
        sample.value
        for sample in _tagged(snapshot.metric_samples, tag)
        if sample.metric_name == metric_name and sample.status == "valid"
    ]


def _aggregate(snapshot: RunSnapshot, metric_name: str, tag: str | None) -> Decimal | None:
    values = _valid_metric_values(snapshot, metric_name, tag)
    if not values:
        return None
    definition = METRIC_BY_NAME[metric_name]
    total = sum(values, Decimal("0"))
    return total if definition.aggregation == "sum" else total / Decimal(len(values))


def _overall_score(snapshot: RunSnapshot, tag: str | None) -> Decimal | None:
    names = snapshot.metric_names or tuple(QUALITY_METRICS)
    values = [
        value
        for name in names
        if name in QUALITY_METRICS
        for value in [_aggregate(snapshot, name, tag)]
        if value is not None
    ]
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _failed_cases(snapshot: RunSnapshot, tag: str | None) -> Decimal:
    if tag is None:
        return Decimal(snapshot.failed_cases)
    return Decimal(
        sum(
            1
            for case in snapshot.cases
            if tag in case.tags and case.status in {"failed", "canceled", "cancelled"}
        )
    )


def _p95_latency(snapshot: RunSnapshot, tag: str | None) -> Decimal | None:
    values = sorted(_valid_metric_values(snapshot, "latency_ms", tag))
    if not values:
        return None
    return values[max(0, math.ceil(len(values) * 0.95) - 1)]


def _value(
    rule: RegressionRule, baseline: RunSnapshot, candidate: RunSnapshot
) -> tuple[Decimal | None, Decimal | None]:
    rule_type = rule.rule_type
    tag = rule.tag
    if rule_type == "minimum_overall_score":
        return _overall_score(baseline, tag), _overall_score(candidate, tag)
    if rule_type == "maximum_score_decrease":
        baseline_score = _overall_score(baseline, tag)
        candidate_score = _overall_score(candidate, tag)
        if baseline_score is None or candidate_score is None:
            return baseline_score, None
        return baseline_score, max(Decimal("0"), baseline_score - candidate_score)
    if rule_type == "maximum_failed_cases":
        return _failed_cases(baseline, tag), _failed_cases(candidate, tag)
    if rule_type == "maximum_p95_latency":
        return _p95_latency(baseline, tag), _p95_latency(candidate, tag)
    if rule_type == "maximum_estimated_cost":
        return _aggregate(baseline, "estimated_cost", tag), _aggregate(
            candidate, "estimated_cost", tag
        )
    if rule_type == "per_metric_threshold" and rule.metric_name in METRIC_BY_NAME:
        return _aggregate(baseline, rule.metric_name, tag), _aggregate(
            candidate, rule.metric_name, tag
        )
    return None, None


def _passes(operator: str, value: Decimal, threshold: Decimal) -> bool:
    return {
        "<": value < threshold,
        "<=": value <= threshold,
        ">": value > threshold,
        ">=": value >= threshold,
        "=": value == threshold,
    }[operator]


def _rule_label(rule: RegressionRule) -> str:
    suffix = f" for tag '{rule.tag}'" if rule.tag else ""
    if rule.rule_type == "per_metric_threshold":
        return f"metric {rule.metric_name}{suffix}"
    return f"{rule.rule_type.replace('_', ' ')}{suffix}"


def evaluate_regression(
    baseline: RunSnapshot,
    candidate: RunSnapshot,
    rules: Sequence[RegressionRule],
) -> RegressionEvaluation:
    evaluated_at = datetime.now(tz=UTC)
    if baseline.status not in {"completed", "partially_failed"}:
        violation = RegressionViolation(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            f"baseline run is not comparable because it is {baseline.status}",
        )
        return RegressionEvaluation("not_evaluable", True, (violation,), evaluated_at)
    if candidate.status != "completed":
        violation = RegressionViolation(
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            f"candidate run is not comparable because it is {candidate.status}",
        )
        return RegressionEvaluation("not_evaluable", True, (violation,), evaluated_at)

    violations: list[RegressionViolation] = []
    for rule in rules:
        baseline_value, candidate_value = _value(rule, baseline, candidate)
        if candidate_value is None:
            violations.append(
                RegressionViolation(
                    rule.id,
                    rule.rule_type,
                    rule.metric_name,
                    rule.tag,
                    baseline_value,
                    candidate_value,
                    rule.threshold,
                    f"rule {_rule_label(rule)} could not be evaluated from stored artifacts",
                )
            )
            continue
        if not _passes(rule.operator, candidate_value, rule.threshold):
            violations.append(
                RegressionViolation(
                    rule.id,
                    rule.rule_type,
                    rule.metric_name,
                    rule.tag,
                    baseline_value,
                    candidate_value,
                    rule.threshold,
                    f"rule {_rule_label(rule)} failed: {candidate_value} {rule.operator} "
                    f"{rule.threshold} is false",
                )
            )
    return RegressionEvaluation(
        "failed" if violations else "passed",
        bool(violations),
        tuple(violations),
        evaluated_at,
    )
