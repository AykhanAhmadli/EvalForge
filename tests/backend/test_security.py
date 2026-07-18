from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from evalforge.config import get_settings
from evalforge_api.security import require_api_key


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def request_with_headers(
    *headers: tuple[str, str], path_params: dict[str, str] | None = None
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/workspaces/workspace-1",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
            "path_params": path_params or {},
        }
    )


def test_auth_disabled_yields_unrestricted_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_AUTH_REQUIRED", raising=False)
    get_settings.cache_clear()

    dependency = require_api_key(request_with_headers())
    principal = next(dependency)
    dependency.close()

    assert principal.workspace_ids is None
    get_settings.cache_clear()


def test_auth_requires_bearer_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("API_KEY_WORKSPACES", "test-key:workspace-1")
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as error:
        next(require_api_key(request_with_headers()))

    assert error.value.status_code == 401
    get_settings.cache_clear()


def test_auth_scopes_principal_to_assigned_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("API_KEY_WORKSPACES", "test-key:workspace-1")
    get_settings.cache_clear()

    dependency = require_api_key(
        request_with_headers(
            ("Authorization", "Bearer test-key"),
            ("X-EvalForge-Workspace-ID", "workspace-1"),
        )
    )
    principal = next(dependency)
    dependency.close()

    assert principal.workspace_ids == frozenset({"workspace-1"})
    get_settings.cache_clear()


def test_auth_rejects_unassigned_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("API_KEY_WORKSPACES", "test-key:workspace-1")
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as error:
        next(
            require_api_key(
                request_with_headers(
                    ("Authorization", "Bearer test-key"),
                    ("X-EvalForge-Workspace-ID", "workspace-2"),
                )
            )
        )

    assert error.value.status_code == 404
    get_settings.cache_clear()
