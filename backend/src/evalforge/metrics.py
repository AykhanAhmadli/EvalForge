from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from jsonschema import Draft202012Validator, SchemaError, ValidationError

MetricDirection = Literal["higher_is_better", "lower_is_better"]
MetricAggregation = Literal["mean", "sum"]


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    display_name: str
    direction: MetricDirection
    semantics: str
    aggregation: MetricAggregation


@dataclass(frozen=True)
class MetricEvaluation:
    value: Decimal
    status: str
    details: dict[str, Any]


def normalize_text(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip())
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "exact_match",
        "Exact Match",
        "higher_is_better",
        "Normalized output and expected value must be identical.",
        "mean",
    ),
    MetricDefinition(
        "case_insensitive_exact_match",
        "Case-insensitive Exact Match",
        "higher_is_better",
        "Normalized output and expected value must be identical after Unicode case folding.",
        "mean",
    ),
    MetricDefinition(
        "contains",
        "Contains",
        "higher_is_better",
        "The normalized expected value must occur as a case-insensitive substring "
        "of the normalized output.",
        "mean",
    ),
    MetricDefinition(
        "regex_match",
        "Regular-expression Match",
        "higher_is_better",
        "The configured regular expression, or expected value when no pattern is "
        "configured, must match the complete output.",
        "mean",
    ),
    MetricDefinition(
        "json_schema_validity",
        "JSON-schema Validity",
        "higher_is_better",
        "The output must be valid JSON and validate against the configured JSON Schema.",
        "mean",
    ),
    MetricDefinition(
        "numeric_tolerance",
        "Numeric Tolerance",
        "higher_is_better",
        "A numeric output is scored 1 when its absolute difference from the expected "
        "number is within tolerance; otherwise it receives a proportional score in [0, 1].",
        "mean",
    ),
    MetricDefinition(
        "semantic_similarity",
        "Semantic Similarity",
        "higher_is_better",
        "Cosine similarity from the deterministic local hash-embedding model, "
        "normalized to [0, 1].",
        "mean",
    ),
    MetricDefinition(
        "latency_ms",
        "Latency",
        "lower_is_better",
        "Provider latency in milliseconds as reported by the adapter.",
        "mean",
    ),
    MetricDefinition(
        "input_tokens",
        "Input Tokens",
        "lower_is_better",
        "Prompt token count reported by the provider adapter.",
        "sum",
    ),
    MetricDefinition(
        "output_tokens",
        "Output Tokens",
        "lower_is_better",
        "Completion token count reported by the provider adapter.",
        "sum",
    ),
    MetricDefinition(
        "estimated_cost",
        "Estimated Cost",
        "lower_is_better",
        "Estimated provider cost using editable pricing effective at run time; currency "
        "and pricing version are preserved in details.",
        "sum",
    ),
)
METRIC_BY_NAME = {definition.name: definition for definition in METRIC_DEFINITIONS}


def list_metric_definitions() -> list[dict[str, str]]:
    return [
        {
            "name": metric.name,
            "display_name": metric.display_name,
            "direction": metric.direction,
            "aggregation": metric.aggregation,
            "semantics": metric.semantics,
        }
        for metric in METRIC_DEFINITIONS
    ]


def _score(value: bool) -> MetricEvaluation:
    return MetricEvaluation(Decimal("1") if value else Decimal("0"), "valid", {"matched": value})


def _invalid(reason: str, **details: Any) -> MetricEvaluation:
    return MetricEvaluation(Decimal("0"), "invalid", {"valid": False, "error": reason, **details})


def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not numeric")
    return float(value)


def _embedding(value: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"[\w]+", value.casefold())
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        for offset in range(0, 8, 2):
            index = int.from_bytes(digest[offset : offset + 2], "big") % dimensions
            vector[index] += 1.0 if digest[offset + 1] % 2 else -1.0
    return vector


def _semantic_similarity(expected: Any, actual: Any) -> MetricEvaluation:
    left = _embedding(normalize_text(expected))
    right = _embedding(normalize_text(actual))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return _invalid("semantic similarity requires non-empty text")
    cosine = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    normalized = max(0.0, min(1.0, (cosine + 1.0) / 2.0))
    return MetricEvaluation(
        Decimal(str(round(normalized, 6))),
        "valid",
        {"cosine": cosine, "model": "local-hash-embedding-v1"},
    )


def evaluate_metric(
    name: str,
    *,
    expected: Any,
    actual: Any,
    latency_ms: int | None = None,
    token_usage: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    pricing: dict[str, Any] | None = None,
) -> MetricEvaluation:
    options = options or {}
    token_usage = token_usage or {}
    if name not in METRIC_BY_NAME:
        return _invalid("unknown metric", metric=name)

    if name == "exact_match":
        return _score(normalize_text(expected) == normalize_text(actual))
    if name == "case_insensitive_exact_match":
        return _score(normalize_text(expected).casefold() == normalize_text(actual).casefold())
    if name == "contains":
        return _score(normalize_text(expected).casefold() in normalize_text(actual).casefold())
    if name == "regex_match":
        pattern = options.get("pattern", normalize_text(expected))
        try:
            matched = re.fullmatch(str(pattern), normalize_text(actual)) is not None
        except re.error as exc:
            return _invalid("invalid regular expression", pattern=str(pattern), message=str(exc))
        return _score(matched)
    if name == "json_schema_validity":
        schema = options.get("schema")
        if not isinstance(schema, dict):
            return _invalid("json schema is not configured")
        try:
            Draft202012Validator.check_schema(schema)
            parsed = json.loads(actual if isinstance(actual, str) else json.dumps(actual))
            Draft202012Validator(schema).validate(parsed)
        except (SchemaError, ValidationError, json.JSONDecodeError, TypeError) as exc:
            return _invalid("output is not valid for the configured JSON schema", message=str(exc))
        return _score(True)
    if name == "numeric_tolerance":
        try:
            expected_number = _number(expected)
            actual_number = _number(actual)
            tolerance = abs(float(options.get("tolerance", 0)))
        except (TypeError, ValueError):
            return _invalid("expected and actual values must be numeric")
        difference = abs(expected_number - actual_number)
        numeric_score = (
            1.0
            if difference <= tolerance
            else (0.0 if tolerance == 0 else max(0.0, 1.0 - difference / tolerance))
        )
        return MetricEvaluation(
            Decimal(str(round(numeric_score, 6))),
            "valid",
            {
                "expected": expected_number,
                "actual": actual_number,
                "difference": difference,
                "tolerance": tolerance,
            },
        )
    if name == "semantic_similarity":
        return _semantic_similarity(expected, actual)
    if name == "latency_ms":
        if latency_ms is None or latency_ms < 0:
            return _invalid("latency was not reported")
        return MetricEvaluation(Decimal(latency_ms), "valid", {"unit": "ms"})
    if name == "input_tokens":
        value = token_usage.get("prompt_tokens")
        return (
            MetricEvaluation(Decimal(value), "valid", {"unit": "tokens"})
            if isinstance(value, int) and value >= 0
            else _invalid("input token count was not reported")
        )
    if name == "output_tokens":
        value = token_usage.get("completion_tokens")
        return (
            MetricEvaluation(Decimal(value), "valid", {"unit": "tokens"})
            if isinstance(value, int) and value >= 0
            else _invalid("output token count was not reported")
        )
    pricing_config = pricing or {}
    input_cost = pricing_config.get("input_cost_per_1k")
    output_cost = pricing_config.get("output_cost_per_1k")
    if input_cost is None or output_cost is None:
        return _invalid("no effective pricing configuration is available")
    prompt_tokens = token_usage.get("prompt_tokens", 0)
    completion_tokens = token_usage.get("completion_tokens", 0)
    value = (
        Decimal(str(input_cost)) * Decimal(prompt_tokens)
        + Decimal(str(output_cost)) * Decimal(completion_tokens)
    ) / Decimal(1000)
    return MetricEvaluation(
        value,
        "valid",
        {
            "currency": pricing_config.get("currency", "USD"),
            "effective_from": str(pricing_config.get("effective_from")),
            "input_cost_per_1k": str(input_cost),
            "output_cost_per_1k": str(output_cost),
        },
    )
