from __future__ import annotations

from collections.abc import Iterator
from contextvars import ContextVar, Token
from dataclasses import dataclass
from secrets import compare_digest
from typing import Any

from fastapi import HTTPException, Request, status

from evalforge.config import get_settings
from evalforge.models import (
    Baseline,
    Dataset,
    DatasetVersion,
    EvaluationResult,
    EvaluationRun,
    MetricResult,
    PromptTemplate,
    PromptVersion,
    RegressionRule,
    RunAggregate,
    TestCase,
    Workspace,
)

_active_workspaces: ContextVar[frozenset[str] | None] = ContextVar(
    "evalforge_active_workspaces", default=None
)


@dataclass(frozen=True)
class ApiPrincipal:
    """Runtime identity for an API key and its explicitly assigned workspaces."""

    workspace_ids: frozenset[str] | None


def _workspace_assignments(value: str) -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []
    for item in value.split(","):
        key, separator, workspace_id = item.strip().partition(":")
        if separator and key and workspace_id:
            assignments.append((key, workspace_id))
    return assignments


def require_api_key(request: Request) -> Iterator[ApiPrincipal]:
    settings = get_settings()
    if not settings.api_auth_required:
        context_token: Token[frozenset[str] | None] = _active_workspaces.set(None)
        try:
            yield ApiPrincipal(None)
        finally:
            _active_workspaces.reset(context_token)
        return

    authorization = request.headers.get("authorization", "")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer API authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    assignments = _workspace_assignments(settings.api_key_workspaces)
    configured_keys = [item.strip() for item in settings.api_keys.split(",") if item.strip()]
    if not assignments or not configured_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key workspace assignments are not configured",
        )
    if not any(compare_digest(key, credential) for key in configured_keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    matching_workspaces = frozenset(
        workspace_id for key, workspace_id in assignments if compare_digest(key, credential)
    )
    if not matching_workspaces:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    requested_workspace = request.headers.get(
        "x-evalforge-workspace-id"
    ) or request.path_params.get("workspace_id")
    if not requested_workspace or requested_workspace not in matching_workspaces:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace is not available to this API key",
        )
    context_token = _active_workspaces.set(matching_workspaces)
    try:
        yield ApiPrincipal(matching_workspaces)
    finally:
        _active_workspaces.reset(context_token)


def ensure_resource_access(session: Any, value: Any) -> None:
    allowed = _active_workspaces.get()
    if allowed is None:
        return
    workspace_id = getattr(value, "workspace_id", None)
    if workspace_id is None:
        if isinstance(value, DatasetVersion):
            parent = session.get(Dataset, value.dataset_id)
        elif isinstance(value, TestCase):
            version = session.get(DatasetVersion, value.dataset_version_id)
            parent = session.get(Dataset, version.dataset_id) if version else None
        elif isinstance(value, PromptVersion):
            parent = session.get(PromptTemplate, value.prompt_template_id)
        elif isinstance(value, (EvaluationResult, MetricResult, RunAggregate)):
            parent = session.get(EvaluationRun, value.run_id)
        elif isinstance(value, RegressionRule):
            parent = session.get(Baseline, value.baseline_id)
        else:
            parent = None
        workspace_id = getattr(parent, "workspace_id", None)
    if isinstance(value, Workspace):
        workspace_id = value.id
    if workspace_id is not None and str(workspace_id) not in allowed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="resource is not available to this API key",
        )


def filter_workspace_rows(rows: list[Any], principal: ApiPrincipal) -> list[Any]:
    if principal.workspace_ids is None:
        return rows
    return [row for row in rows if str(row.id) in principal.workspace_ids]
