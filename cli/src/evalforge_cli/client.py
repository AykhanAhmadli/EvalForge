from __future__ import annotations

import os
from typing import Any

import httpx


class CLIError(RuntimeError):
    """An expected CLI or API error that is safe to show to the user."""


class UnreachableServerError(CLIError):
    """The configured API could not be reached."""


class EvalForgeClient:
    def __init__(self, api_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        self.api_url = api_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.api_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise UnreachableServerError(
                f"EvalForge API is unreachable: {exc.__class__.__name__}"
            ) from exc
        if not response.is_success:
            detail: Any = None
            try:
                detail = response.json().get("detail")
            except ValueError:
                pass
            message = (
                detail
                if isinstance(detail, str)
                else f"API request failed with HTTP {response.status_code}"
            )
            raise CLIError(message)
        if response.status_code == 204:
            return None
        return response.json()

    def start_suite(self, workspace_id: str, suite_id: str) -> dict[str, Any]:
        return self.request(
            "POST", f"/api/v1/workspaces/{workspace_id}/suites/{suite_id}/runs", json={}
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/evaluation-runs/{run_id}")

    def compare(self, baseline_id: str, candidate_run_id: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/v1/baselines/{baseline_id}/compare",
            params={"candidate_run_id": candidate_run_id},
        )

    def export_results(self, run_id: str) -> list[dict[str, Any]]:
        return self.request("GET", f"/api/v1/evaluation-runs/{run_id}/results")

    def health(self) -> dict[str, Any]:
        return self.request("GET", "/health/live")


def client_from_environment(api_url: str | None = None) -> EvalForgeClient:
    resolved_url = api_url or str(os.getenv("EVALFORGE_API_URL", "http://localhost:8000"))
    api_key = os.getenv("EVALFORGE_API_KEY")
    if not api_key:
        raise CLIError("EVALFORGE_API_KEY is required")
    return EvalForgeClient(resolved_url, api_key)


def workspace_from_environment(workspace_id: str | None = None) -> str:
    resolved = workspace_id or os.getenv("EVALFORGE_WORKSPACE_ID")
    if not resolved:
        raise CLIError("EVALFORGE_WORKSPACE_ID is required")
    return resolved
