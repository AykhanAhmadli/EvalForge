from __future__ import annotations

import hashlib

from evalforge.providers.base import (
    PermanentProviderError,
    ProviderRequest,
    ProviderResponse,
    TransientProviderError,
)


class FakeProvider:
    name = "fake"

    def __init__(self, seed: str) -> None:
        self.seed = seed

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        transient_failures = int(request.parameters.get("transient_failures", 0))
        attempt = int(request.metadata.get("job_attempt", 1))
        if attempt <= transient_failures:
            raise TransientProviderError("fake provider transient failure")
        permanent_inputs = request.parameters.get("permanent_failure_substrings", [])
        if any(str(value) in request.prompt for value in permanent_inputs):
            raise PermanentProviderError("fake provider permanent failure")
        digest = hashlib.sha256(
            f"{self.seed}:{request.model_name}:{request.prompt}".encode()
        ).hexdigest()
        output = f"fake-output-{digest[:16]}"
        return ProviderResponse(
            output_text=output,
            latency_ms=0,
            token_usage={
                "prompt_tokens": len(request.prompt.split()),
                "completion_tokens": 1,
                "total_tokens": len(request.prompt.split()) + 1,
            },
            provider_trace_id=f"fake-{digest[:12]}",
        )
