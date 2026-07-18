from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderRequest:
    prompt: str
    model_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    output_text: str
    latency_ms: int
    token_usage: dict[str, int]
    provider_trace_id: str


class ModelProvider(Protocol):
    name: str

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate a model response through a provider adapter."""
