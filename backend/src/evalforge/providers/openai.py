from __future__ import annotations

import os
import time
from typing import Any

import httpx

from evalforge.providers.base import (
    PermanentProviderError,
    ProviderRequest,
    ProviderResponse,
    TransientProviderError,
)


class ProviderConfigurationError(RuntimeError):
    pass


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, timeout_seconds: int) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ProviderConfigurationError("OPENAI_API_KEY is not configured")
        self._api_key = api_key
        self._base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self._timeout_seconds = timeout_seconds

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": request.model_name,
                    "messages": [{"role": "user", "content": request.prompt}],
                    **request.parameters,
                },
                timeout=self._timeout_seconds,
            )
        except httpx.RequestError as exc:
            raise TransientProviderError("provider request failed before a response") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientProviderError(
                f"provider returned retryable status {response.status_code}"
            )
        if response.is_error:
            raise PermanentProviderError(f"provider returned status {response.status_code}")
        payload = response.json()
        choice = payload.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = payload.get("usage", {})
        return ProviderResponse(
            output_text=str(message.get("content", "")),
            latency_ms=round((time.perf_counter() - started) * 1000),
            token_usage={
                "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                "completion_tokens": int(usage.get("completion_tokens", 0)),
                "total_tokens": int(usage.get("total_tokens", 0)),
            },
            provider_trace_id=str(payload.get("id", "")),
        )


def available_provider_names() -> list[str]:
    return ["fake", "openai"]


def build_provider(*, provider: str, timeout_seconds: int, seed: str) -> Any:
    if provider == "fake":
        from evalforge.providers.fake import FakeProvider

        return FakeProvider(seed)
    if provider == "openai":
        return OpenAIProvider(timeout_seconds=timeout_seconds)
    raise ProviderConfigurationError(f"unsupported provider: {provider}")
