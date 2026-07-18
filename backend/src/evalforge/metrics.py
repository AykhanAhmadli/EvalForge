from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MetricDirection = Literal["higher_is_better", "lower_is_better"]


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    display_name: str
    direction: MetricDirection
    semantics: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        name="exact_match",
        display_name="Exact Match",
        direction="higher_is_better",
        semantics=(
            "Returns 1.0 when normalized model output exactly equals normalized expected "
            "output, otherwise 0.0. Aggregates by arithmetic mean."
        ),
    ),
    MetricDefinition(
        name="contains_expected",
        display_name="Contains Expected",
        direction="higher_is_better",
        semantics=(
            "Returns 1.0 when normalized expected output appears as a case-insensitive "
            "substring of normalized model output, otherwise 0.0. Aggregates by arithmetic mean."
        ),
    ),
)


def list_metric_definitions() -> list[dict[str, str]]:
    return [
        {
            "name": metric.name,
            "display_name": metric.display_name,
            "direction": metric.direction,
            "semantics": metric.semantics,
        }
        for metric in METRIC_DEFINITIONS
    ]
