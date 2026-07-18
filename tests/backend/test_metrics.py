from __future__ import annotations

from decimal import Decimal

from evalforge.metrics import evaluate_metric, list_metric_definitions


def test_metric_registry_documents_all_required_metrics() -> None:
    names = {metric["name"] for metric in list_metric_definitions()}
    assert names == {
        "exact_match",
        "case_insensitive_exact_match",
        "contains",
        "regex_match",
        "json_schema_validity",
        "numeric_tolerance",
        "semantic_similarity",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "estimated_cost",
    }


def test_text_and_numeric_metrics_are_normalized() -> None:
    assert evaluate_metric("exact_match", expected=" hello ", actual="hello").value == Decimal("1")
    assert evaluate_metric(
        "case_insensitive_exact_match", expected="Hello", actual="hello"
    ).value == Decimal("1")
    assert evaluate_metric("contains", expected="world", actual="Hello WORLD").value == Decimal("1")
    assert evaluate_metric(
        "numeric_tolerance", expected=10, actual=10.5, options={"tolerance": 1}
    ).value == Decimal("1")
    assert evaluate_metric(
        "numeric_tolerance", expected=10, actual=11.5, options={"tolerance": 1}
    ).value == Decimal("0.5")


def test_invalid_metric_inputs_are_preserved_as_invalid() -> None:
    regex = evaluate_metric("regex_match", expected="[", actual="value")
    schema = evaluate_metric("json_schema_validity", expected="", actual="{}")
    numeric = evaluate_metric("numeric_tolerance", expected="ten", actual="10")
    assert regex.status == schema.status == numeric.status == "invalid"
    assert regex.details["valid"] is False


def test_local_semantic_metric_is_deterministic_and_cost_uses_editable_pricing() -> None:
    first = evaluate_metric("semantic_similarity", expected="alpha beta", actual="alpha beta")
    second = evaluate_metric("semantic_similarity", expected="alpha beta", actual="alpha beta")
    cost = evaluate_metric(
        "estimated_cost",
        expected="ignored",
        actual="ignored",
        token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        pricing={
            "input_cost_per_1k": Decimal("0.01"),
            "output_cost_per_1k": Decimal("0.02"),
            "currency": "USD",
            "effective_from": "2026-01-01",
        },
    )
    assert first.value == second.value
    assert cost.value == Decimal("0.002")
    assert cost.details["effective_from"] == "2026-01-01"
