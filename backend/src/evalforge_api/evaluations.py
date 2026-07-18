from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evalforge.db import get_session
from evalforge.enums import EvaluationRunStatus, JobKind, JobStatus
from evalforge.metrics import METRIC_BY_NAME, METRIC_DEFINITIONS
from evalforge.models import (
    Baseline,
    Dataset,
    DatasetVersion,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    Job,
    MetricResult,
    ModelConfiguration,
    PromptTemplate,
    PromptVersion,
    ProviderPricing,
    RegressionRule,
    RunAggregate,
    TestCase,
    Workspace,
)
from evalforge.regression import (
    CaseSample,
    MetricSample,
    RunSnapshot,
    evaluate_regression,
)
from evalforge.schemas import (
    BaselineCreate,
    BaselineResponse,
    EvaluationAggregateResponse,
    EvaluationResultResponse,
    EvaluationRunCreate,
    EvaluationRunResponse,
    MetricResultResponse,
    ProviderPricingCreate,
    ProviderPricingResponse,
    ProviderPricingUpdate,
    RegressionComparisonResponse,
    RegressionRuleCreate,
    RegressionRuleResponse,
    RegressionViolationResponse,
    SuiteRunCreate,
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


def _create_evaluation_run(
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
    return _create_evaluation_run(workspace_id, payload, session)


@router.post(
    "/workspaces/{workspace_id}/suites/{suite_id}/runs",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_suite_run(
    workspace_id: UUID,
    suite_id: UUID,
    payload: SuiteRunCreate,
    session: Session = Depends(get_session),
) -> EvaluationRunResponse:
    suite = require(session, EvaluationSuite, suite_id, "evaluation suite")
    if suite.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="evaluation suite not found in workspace")
    if (
        not suite.dataset_version_id
        or not suite.prompt_version_id
        or not suite.model_configuration_id
    ):
        raise HTTPException(status_code=422, detail="evaluation suite is not fully configured")
    return _create_evaluation_run(
        workspace_id,
        EvaluationRunCreate(
            dataset_version_id=suite.dataset_version_id,
            prompt_version_id=suite.prompt_version_id,
            model_configuration_id=suite.model_configuration_id,
            suite_id=suite.id,
            requested_by=payload.requested_by,
            metrics=payload.metrics or suite.metric_names or None,
            metric_options=payload.metric_options
            if payload.metric_options is not None
            else suite.metric_options,
        ),
        session,
    )


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


@router.get("/evaluation-runs/{run_id}/metric-results", response_model=list[MetricResultResponse])
def list_metric_results(
    run_id: UUID, session: Session = Depends(get_session)
) -> list[MetricResultResponse]:
    require(session, EvaluationRun, run_id, "evaluation run")
    results = session.scalars(
        select(MetricResult)
        .where(MetricResult.run_id == run_id)
        .order_by(MetricResult.test_case_id, MetricResult.metric_name)
    ).all()
    return [MetricResultResponse.model_validate(result) for result in results]


def _run_snapshot(session: Session, run: EvaluationRun) -> RunSnapshot:
    metric_rows = session.execute(
        select(MetricResult, TestCase)
        .join(TestCase, TestCase.id == MetricResult.test_case_id)
        .where(MetricResult.run_id == run.id)
    ).all()
    result_rows = session.execute(
        select(EvaluationResult, TestCase)
        .join(TestCase, TestCase.id == EvaluationResult.test_case_id)
        .where(EvaluationResult.run_id == run.id)
    ).all()
    return RunSnapshot(
        run_id=run.id,
        status=run.status,
        failed_cases=run.failed_cases,
        metric_names=tuple(run.metric_names),
        metric_samples=tuple(
            MetricSample(
                metric_name=metric.metric_name,
                value=metric.value,
                status=metric.status,
                tags=tuple(test_case.tags or []),
            )
            for metric, test_case in metric_rows
        ),
        cases=tuple(
            CaseSample(status=result.status, tags=tuple(test_case.tags or []))
            for result, test_case in result_rows
        ),
    )


@router.post(
    "/baselines/{baseline_id}/compare",
    response_model=RegressionComparisonResponse,
)
def compare_baseline(
    baseline_id: UUID,
    candidate_run_id: UUID,
    session: Session = Depends(get_session),
) -> RegressionComparisonResponse:
    baseline = require(session, Baseline, baseline_id, "baseline")
    baseline_run = require(session, EvaluationRun, baseline.evaluation_run_id, "baseline run")
    candidate_run = require(session, EvaluationRun, candidate_run_id, "candidate run")
    if baseline.workspace_id != candidate_run.workspace_id:
        raise HTTPException(status_code=404, detail="candidate run not found in baseline workspace")
    rules = session.scalars(
        select(RegressionRule)
        .where(RegressionRule.baseline_id == baseline.id)
        .order_by(RegressionRule.created_at, RegressionRule.id)
    ).all()
    evaluation = evaluate_regression(
        _run_snapshot(session, baseline_run), _run_snapshot(session, candidate_run), rules
    )
    return RegressionComparisonResponse(
        baseline_id=baseline.id,
        baseline_run_id=baseline_run.id,
        candidate_run_id=candidate_run.id,
        status=cast(Literal["passed", "failed", "not_evaluable"], evaluation.status),
        regression_detected=evaluation.regression_detected,
        violations=[
            RegressionViolationResponse(
                rule_id=violation.rule_id,
                rule_type=violation.rule_type,
                metric_name=violation.metric_name,
                tag=violation.tag,
                baseline_value=violation.baseline_value,
                candidate_value=violation.candidate_value,
                threshold=violation.threshold,
                message=violation.message,
            )
            for violation in evaluation.violations
        ],
        evaluated_at=evaluation.evaluated_at,
    )


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


def _baseline_response(session: Session, baseline: Baseline) -> BaselineResponse:
    rules = session.scalars(
        select(RegressionRule)
        .where(RegressionRule.baseline_id == baseline.id)
        .order_by(RegressionRule.metric_name)
    ).all()
    return BaselineResponse(
        id=baseline.id,
        workspace_id=baseline.workspace_id,
        name=baseline.name,
        evaluation_run_id=baseline.evaluation_run_id,
        rules=[RegressionRuleResponse.model_validate(rule) for rule in rules],
    )


@router.post(
    "/workspaces/{workspace_id}/baselines",
    response_model=BaselineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_baseline(
    workspace_id: UUID,
    payload: BaselineCreate,
    session: Session = Depends(get_session),
) -> BaselineResponse:
    require(session, Workspace, workspace_id, "workspace")
    run = require(session, EvaluationRun, payload.evaluation_run_id, "evaluation run")
    if run.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="evaluation run not found in workspace")
    if run.status not in {"completed", "partially_failed"}:
        raise HTTPException(status_code=422, detail="only finished runs can be baselines")
    baseline = Baseline(
        workspace_id=workspace_id,
        name=payload.name,
        evaluation_run_id=payload.evaluation_run_id,
    )
    session.add(baseline)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="a baseline with this name already exists"
        ) from exc
    session.refresh(baseline)
    return _baseline_response(session, baseline)


@router.get("/workspaces/{workspace_id}/baselines", response_model=list[BaselineResponse])
def list_baselines(
    workspace_id: UUID, session: Session = Depends(get_session)
) -> list[BaselineResponse]:
    require(session, Workspace, workspace_id, "workspace")
    baselines = session.scalars(
        select(Baseline).where(Baseline.workspace_id == workspace_id).order_by(Baseline.name)
    ).all()
    return [_baseline_response(session, baseline) for baseline in baselines]


@router.delete("/baselines/{baseline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_baseline(baseline_id: UUID, session: Session = Depends(get_session)) -> Response:
    baseline = require(session, Baseline, baseline_id, "baseline")
    session.delete(baseline)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/baselines/{baseline_id}/rules",
    response_model=RegressionRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_regression_rule(
    baseline_id: UUID,
    payload: RegressionRuleCreate,
    session: Session = Depends(get_session),
) -> RegressionRule:
    require(session, Baseline, baseline_id, "baseline")
    expected_operators = {
        "minimum_overall_score": ">=",
        "maximum_score_decrease": "<=",
        "maximum_failed_cases": "<=",
        "maximum_p95_latency": "<=",
        "maximum_estimated_cost": "<=",
    }
    if payload.rule_type == "per_metric_threshold" and payload.metric_name not in METRIC_BY_NAME:
        raise HTTPException(status_code=422, detail="metric is not registered")
    if payload.rule_type != "per_metric_threshold" and payload.metric_name is not None:
        raise HTTPException(status_code=422, detail="metric_name is only valid for metric rules")
    expected_operator = expected_operators.get(payload.rule_type)
    if expected_operator and payload.operator != expected_operator:
        raise HTTPException(
            status_code=422,
            detail=f"{payload.rule_type} rules must use operator {expected_operator}",
        )
    rule = RegressionRule(
        baseline_id=baseline_id,
        rule_type=payload.rule_type,
        metric_name=payload.metric_name,
        tag=payload.tag,
        operator=payload.operator,
        threshold=payload.threshold,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.delete("/regression-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_regression_rule(rule_id: UUID, session: Session = Depends(get_session)) -> Response:
    rule = require(session, RegressionRule, rule_id, "regression rule")
    session.delete(rule)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
