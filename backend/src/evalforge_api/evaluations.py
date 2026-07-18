from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evalforge.db import get_session
from evalforge.enums import EvaluationRunStatus, JobKind, JobStatus
from evalforge.metrics import METRIC_BY_NAME, METRIC_DEFINITIONS
from evalforge.models import (
    Dataset,
    DatasetVersion,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    Job,
    ModelConfiguration,
    PromptTemplate,
    PromptVersion,
    ProviderPricing,
    RunAggregate,
    TestCase,
    Workspace,
)
from evalforge.schemas import (
    EvaluationAggregateResponse,
    EvaluationResultResponse,
    EvaluationRunCreate,
    EvaluationRunResponse,
    ProviderPricingCreate,
    ProviderPricingResponse,
    ProviderPricingUpdate,
)
from evalforge.validation import ParsedTestCase, validate_template_variables

router = APIRouter(prefix="/api/v1", tags=["evaluations"])
DEFAULT_METRICS = [definition.name for definition in METRIC_DEFINITIONS]


def now() -> datetime:
    return datetime.now(tz=UTC)


def require(session: Session, model: type[Any], object_id: UUID, label: str) -> Any:
    value = session.get(model, object_id)
    if value is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return value


def _aggregates(session: Session, run_id: UUID) -> list[EvaluationAggregateResponse]:
    values = session.scalars(
        select(RunAggregate)
        .where(RunAggregate.run_id == run_id)
        .order_by(RunAggregate.scope_type, RunAggregate.scope_key, RunAggregate.metric_name)
    ).all()
    return [EvaluationAggregateResponse.model_validate(value) for value in values]


def _run_response(session: Session, run: EvaluationRun) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        id=run.id,
        workspace_id=run.workspace_id,
        suite_id=run.suite_id,
        dataset_version_id=run.dataset_version_id,
        prompt_version_id=run.prompt_version_id,
        model_configuration_id=run.model_configuration_id,
        status=run.status,
        requested_by=run.requested_by,
        failure_reason=run.failure_reason,
        queued_at=run.queued_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        cancelled_at=run.cancelled_at,
        cancel_requested_at=run.cancel_requested_at,
        total_cases=run.total_cases,
        completed_cases=run.completed_cases,
        failed_cases=run.failed_cases,
        metric_names=run.metric_names,
        aggregates=_aggregates(session, run.id),
    )


@router.post(
    "/workspaces/{workspace_id}/evaluation-runs",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_evaluation_run(
    workspace_id: UUID,
    payload: EvaluationRunCreate,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    require(session, Workspace, workspace_id, "workspace")
    dataset_version = require(
        session, DatasetVersion, payload.dataset_version_id, "dataset version"
    )
    prompt_version = require(session, PromptVersion, payload.prompt_version_id, "prompt version")
    model_configuration = require(
        session, ModelConfiguration, payload.model_configuration_id, "model configuration"
    )
    dataset = require(session, Dataset, dataset_version.dataset_id, "dataset")
    prompt_template = require(
        session, PromptTemplate, prompt_version.prompt_template_id, "prompt template"
    )
    if (
        dataset.workspace_id != workspace_id
        or prompt_template.workspace_id != workspace_id
        or model_configuration.workspace_id != workspace_id
    ):
        raise HTTPException(status_code=404, detail="evaluation resource not found in workspace")
    if payload.suite_id is not None:
        suite = require(session, EvaluationSuite, payload.suite_id, "evaluation suite")
        if suite.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="evaluation suite not found in workspace")
    cases = session.scalars(
        select(TestCase)
        .where(TestCase.dataset_version_id == dataset_version.id)
        .order_by(TestCase.row_number)
    ).all()
    _, missing_by_row = validate_template_variables(
        prompt_version.variables,
        [
            ParsedTestCase(
                case.row_number,
                case.input,
                case.expected_output,
                case.row_metadata,
                case.tags,
            )
            for case in cases
        ],
    )
    if missing_by_row:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "prompt variables are missing from the dataset",
                "missing_variables_by_row": missing_by_row,
            },
        )
    metric_names = payload.metrics or DEFAULT_METRICS
    unknown = sorted(set(metric_names) - set(METRIC_BY_NAME))
    if unknown:
        raise HTTPException(
            status_code=422, detail={"message": "unknown metrics", "metrics": unknown}
        )
    run = EvaluationRun(
        workspace_id=workspace_id,
        suite_id=payload.suite_id,
        dataset_version_id=payload.dataset_version_id,
        prompt_version_id=payload.prompt_version_id,
        model_configuration_id=payload.model_configuration_id,
        status=EvaluationRunStatus.queued.value,
        requested_by=payload.requested_by,
        queued_at=now(),
        total_cases=dataset_version.row_count,
        metric_names=metric_names,
        metric_options=payload.metric_options,
    )
    session.add(run)
    session.flush()
    session.add(
        Job(
            kind=JobKind.evaluation_run.value,
            payload={"run_id": str(run.id)},
            status=JobStatus.queued.value,
            run_after=now(),
        )
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="evaluation run could not be created") from exc
    session.refresh(run)
    return _run_response(session, run)


@router.get(
    "/workspaces/{workspace_id}/evaluation-runs", response_model=list[EvaluationRunResponse]
)
def list_evaluation_runs(
    workspace_id: UUID, session: Session = Depends(get_session)
) -> list[EvaluationRunResponse]:
    require(session, Workspace, workspace_id, "workspace")
    runs = session.scalars(
        select(EvaluationRun)
        .where(EvaluationRun.workspace_id == workspace_id)
        .order_by(EvaluationRun.created_at.desc())
    ).all()
    return [_run_response(session, run) for run in runs]


@router.get("/evaluation-runs/{run_id}", response_model=EvaluationRunResponse)
def get_evaluation_run(
    run_id: UUID, session: Session = Depends(get_session)
) -> EvaluationRunResponse:
    run = require(session, EvaluationRun, run_id, "evaluation run")
    return _run_response(session, run)


@router.get("/evaluation-runs/{run_id}/results", response_model=list[EvaluationResultResponse])
def list_evaluation_results(
    run_id: UUID, session: Session = Depends(get_session)
) -> list[EvaluationResultResponse]:
    require(session, EvaluationRun, run_id, "evaluation run")
    results = session.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.run_id == run_id)
        .order_by(EvaluationResult.created_at, EvaluationResult.test_case_id)
    ).all()
    return [EvaluationResultResponse.model_validate(result) for result in results]


@router.post("/evaluation-runs/{run_id}/cancel", response_model=EvaluationRunResponse)
def cancel_evaluation_run(
    run_id: UUID, session: Session = Depends(get_session)
) -> EvaluationRunResponse:
    run = require(session, EvaluationRun, run_id, "evaluation run")
    if run.status in {"completed", "partially_failed", "failed", "cancelled", "canceled"}:
        return _run_response(session, run)
    run.cancel_requested_at = now()
    job = session.scalar(
        select(Job).where(
            Job.kind == JobKind.evaluation_run.value,
            Job.payload["run_id"].as_string() == str(run_id),
        )
    )
    if run.status == EvaluationRunStatus.queued.value:
        run.status = EvaluationRunStatus.cancelled.value
        run.cancelled_at = now()
        if job is not None and job.status == JobStatus.queued.value:
            job.status = JobStatus.canceled.value
            job.completed_at = now()
    session.commit()
    session.refresh(run)
    return _run_response(session, run)


@router.post(
    "/workspaces/{workspace_id}/provider-pricing",
    response_model=ProviderPricingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_pricing(
    workspace_id: UUID,
    payload: ProviderPricingCreate,
    session: Session = Depends(get_session),
) -> ProviderPricing:
    require(session, Workspace, workspace_id, "workspace")
    pricing = ProviderPricing(workspace_id=workspace_id, **payload.model_dump())
    session.add(pricing)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="pricing with this effective date already exists"
        ) from exc
    session.refresh(pricing)
    return pricing


@router.get(
    "/workspaces/{workspace_id}/provider-pricing", response_model=list[ProviderPricingResponse]
)
def list_provider_pricing(
    workspace_id: UUID, session: Session = Depends(get_session)
) -> list[ProviderPricing]:
    require(session, Workspace, workspace_id, "workspace")
    return list(
        session.scalars(
            select(ProviderPricing)
            .where(ProviderPricing.workspace_id == workspace_id)
            .order_by(
                ProviderPricing.provider,
                ProviderPricing.model_name,
                ProviderPricing.effective_from.desc(),
            )
        ).all()
    )


@router.patch("/provider-pricing/{pricing_id}", response_model=ProviderPricingResponse)
def update_provider_pricing(
    pricing_id: UUID,
    payload: ProviderPricingUpdate,
    session: Session = Depends(get_session),
) -> ProviderPricing:
    pricing = require(session, ProviderPricing, pricing_id, "provider pricing")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(pricing, field, value)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="pricing could not be updated") from exc
    session.refresh(pricing)
    return pricing
