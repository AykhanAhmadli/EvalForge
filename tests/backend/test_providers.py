from __future__ import annotations

import pytest

from evalforge.providers import ProviderConfigurationError, build_provider
from evalforge.providers.base import ProviderRequest
from evalforge.providers.fake import FakeProvider


def test_fake_provider_is_deterministic() -> None:
    request = ProviderRequest(prompt="Answer: 2 + 2", model_name="fake-v1")
    first = FakeProvider("unit-seed").generate(request)
    second = FakeProvider("unit-seed").generate(request)

    assert first == second
    assert first.output_text.startswith("fake-output-")


def test_provider_factory_does_not_require_secrets_for_fake() -> None:
    provider = build_provider(provider="fake", timeout_seconds=10, seed="unit-seed")

    assert provider.name == "fake"


def test_openai_provider_requires_environment_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        build_provider(provider="openai", timeout_seconds=10, seed="unit-seed")
