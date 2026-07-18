from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from evalforge.metrics import METRIC_BY_NAME, evaluate_metric
from evalforge.models import (
    Dataset,
    DatasetVersion,
    EvaluationResult,
    EvaluationRun,
    MetricResult,
    ModelConfiguration,
    PromptVersion,
    ProviderPricing,
    RunAggregate,
    TestCase,
)
from evalforge.providers import (
    PermanentProviderError,
    ProviderRequest,
    TransientProviderError,
    build_provider,
)

VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][\w.]*)\s*}}")


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _lookup(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def render_prompt(template: str, input_value: Any) -> str:
    def replace(match: re.Match[str]) -> str:
        try:
            value = _lookup(input_value, match.group(1))
        except KeyError as exc:
            raise ValueError(f"input is missing prompt variable: {exc.args[0]}") from exc
        if isinstance(value, str):
            return value
        return json.dumps(value, sort_keys=True)

    return VARIABLE_PATTERN.sub(replace, template)


class EvaluationEngine:
    def __init__(self, *, provider_seed: str = "evalforge-local") -> None:
        self.provider_seed = provider_seed

    def execute(
        self,
        session: Session,
        run: EvaluationRun,
        *,
        job_attempt: int = 1,
        lease_heartbeat: Callable[[], None] | None = None,
    ) -> None:
        dataset_version = session.get(DatasetVersion, run.dataset_version_id)
        prompt_version = session.get(PromptVersion, run.prompt_version_id)
        model_configuration = session.get(ModelConfiguration, run.model_configuration_id)
        if dataset_version is None or prompt_version is None or model_configuration is None:
            raise ValueError("evaluation references a missing version or model configuration")

        if run.cancel_requested_at is not None:
            self._cancel_run(session, run)
            return

        run.status = "running"
        run.started_at = run.started_at or utcnow()
        run.total_cases = dataset_version.row_count
        session.commit()

        provider = build_provider(
            provider=model_configuration.provider,
            timeout_seconds=model_configuration.timeout_seconds,
            seed=self.provider_seed,
        )
        pricing = self._pricing(session, run.workspace_id, model_configuration, utcnow())
        cases = session.scalars(
            select(TestCase)
            .where(TestCase.dataset_version_id == dataset_version.id)
            .order_by(TestCase.row_number)
        ).all()
        for test_case in cases:
            if lease_heartbeat is not None:
                lease_heartbeat()
            session.refresh(run)
            if run.cancel_requested_at is not None:
                self._cancel_run(session, run)
                return
            existing = session.scalar(
                select(EvaluationResult).where(
                    EvaluationResult.run_id == run.id,
                    EvaluationResult.test_case_id == test_case.id,
                )
            )
            if existing is not None and existing.status == "completed":
                continue
            result = existing or EvaluationResult(
                run_id=run.id,
                test_case_id=test_case.id,
                output={},
                status="running",
            )
            result.status = "running"
            result.output = {}
            result.error_type = None
            result.error_message = None
            result.started_at = utcnow()
            session.add(result)
            session.flush()
            session.execute(
                delete(MetricResult).where(
                    MetricResult.run_id == run.id,
                    MetricResult.test_case_id == test_case.id,
                )
            )
            session.commit()

            try:
                prompt = render_prompt(prompt_version.template, test_case.input)
                request = ProviderRequest(
                    prompt=prompt,
                    model_name=model_configuration.model_name,
                    parameters={
                        **model_configuration.parameters,
                        "temperature": float(model_configuration.temperature),
                        "max_tokens": model_configuration.max_tokens,
                    },
                    metadata={
                        "run_id": str(run.id),
                        "test_case_id": str(test_case.id),
                        "job_attempt": job_attempt,
                    },
                )
                started = time.perf_counter()
                response = provider.generate(request)
                elapsed_ms = round((time.perf_counter() - started) * 1000)
            except TransientProviderError:
                result.status = "retrying"
                result.error_type = "transient_provider_error"
                result.error_message = "provider request will be retried"
                result.completed_at = utcnow()
                session.commit()
                raise
            except (PermanentProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
                result.status = "failed"
                result.error_type = type(exc).__name__
                result.error_message = str(exc)
                result.completed_at = utcnow()
                run.failed_cases += 1
                session.commit()
                continue

            token_usage = response.token_usage
            result.status = "completed"
            result.output = {"text": response.output_text}
            result.latency_ms = response.latency_ms if response.latency_ms >= 0 else elapsed_ms
            result.token_usage = token_usage
            result.provider_trace_id = response.provider_trace_id
            result.completed_at = utcnow()
            for metric_name in run.metric_names:
                evaluation = evaluate_metric(
                    metric_name,
                    expected=test_case.expected_output,
                    actual=response.output_text,
                    latency_ms=result.latency_ms,
                    token_usage=token_usage,
                    options=run.metric_options.get(metric_name, {}),
                    pricing=pricing,
                )
                details = {
                    **evaluation.details,
                    "expected": test_case.expected_output,
                    "actual": response.output_text,
                }
                session.add(
                    MetricResult(
                        run_id=run.id,
                        test_case_id=test_case.id,
                        metric_name=metric_name,
                        value=evaluation.value,
                        status=evaluation.status,
                        details=details,
                    )
                )
            run.completed_cases += 1
            session.commit()
            if lease_heartbeat is not None:
                lease_heartbeat()

        session.refresh(run)
        if run.cancel_requested_at is not None:
            self._cancel_run(session, run)
            return
        run.completed_at = utcnow()
        if run.failed_cases == 0:
            run.status = "completed"
        elif run.completed_cases > 0:
            run.status = "partially_failed"
        else:
            run.status = "failed"
        self.aggregate(session, run)
        session.commit()

    def aggregate(self, session: Session, run: EvaluationRun) -> None:
        session.execute(delete(RunAggregate).where(RunAggregate.run_id == run.id))
        dataset = session.get(DatasetVersion, run.dataset_version_id)
        if dataset is None:
            return
        dataset_parent = session.get(Dataset, dataset.dataset_id)
        rows = session.execute(
            select(MetricResult, TestCase)
            .join(TestCase, TestCase.id == MetricResult.test_case_id)
            .where(MetricResult.run_id == run.id)
        ).all()
        grouped: dict[tuple[str, str, str], list[MetricResult]] = defaultdict(list)
        for metric_result, test_case in rows:
            scopes = {
                "run": str(run.id),
                "dataset": str(dataset_parent.id) if dataset_parent else str(dataset.dataset_id),
                "prompt_version": str(run.prompt_version_id),
                "model_configuration": str(run.model_configuration_id),
            }
            for scope_type, scope_key in scopes.items():
                grouped[(scope_type, scope_key, metric_result.metric_name)].append(metric_result)
            for tag in test_case.tags or ["untagged"]:
                grouped[("tag", str(tag), metric_result.metric_name)].append(metric_result)

        for (scope_type, scope_key, metric_name), values in grouped.items():
            definition = METRIC_BY_NAME[metric_name]
            valid = [value for value in values if value.status == "valid"]
            numeric = [value.value for value in valid]
            aggregate_value: Decimal | None = None
            if numeric:
                aggregate_value = sum(numeric, Decimal("0"))
                if definition.aggregation == "mean":
                    aggregate_value /= Decimal(len(numeric))
            aggregate_status = "valid" if valid and len(valid) == len(values) else "partial"
            if not valid:
                aggregate_status = "invalid"
            session.add(
                RunAggregate(
                    run_id=run.id,
                    scope_type=scope_type,
                    scope_key=scope_key,
                    metric_name=metric_name,
                    value=aggregate_value,
                    sample_count=len(valid),
                    status=aggregate_status,
                    details={
                        "aggregation": definition.aggregation,
                        "invalid_count": len(values) - len(valid),
                    },
                )
            )

    @staticmethod
    def _pricing(
        session: Session,
        workspace_id: UUID,
        model_configuration: ModelConfiguration,
        at: datetime,
    ) -> dict[str, Any] | None:
        price = session.scalar(
            select(ProviderPricing)
            .where(
                ProviderPricing.workspace_id == workspace_id,
                ProviderPricing.provider == model_configuration.provider,
                ProviderPricing.model_name == model_configuration.model_name,
                ProviderPricing.effective_from <= at,
                (ProviderPricing.effective_to.is_(None) | (ProviderPricing.effective_to > at)),
            )
            .order_by(ProviderPricing.effective_from.desc())
        )
        if price is None:
            return None
        return {
            "input_cost_per_1k": price.input_cost_per_1k,
            "output_cost_per_1k": price.output_cost_per_1k,
            "currency": price.currency,
            "effective_from": price.effective_from,
        }

    @staticmethod
    def _cancel_run(session: Session, run: EvaluationRun) -> None:
        run.status = "cancelled"
        run.cancelled_at = utcnow()
        run.completed_at = run.completed_at or run.cancelled_at
        session.commit()
