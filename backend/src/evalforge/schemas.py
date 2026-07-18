from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class WorkspaceCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None


class WorkspaceUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None


class WorkspaceResponse(APIModel):
    id: UUID
    name: str
    slug: str
    description: str | None


class EvaluationSuiteCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    dataset_version_id: UUID | None = None
    prompt_version_id: UUID | None = None
    model_configuration_id: UUID | None = None
    metric_names: list[str] = Field(default_factory=list, max_length=32)
    metric_options: dict[str, Any] = Field(default_factory=dict)


class EvaluationSuiteUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    dataset_version_id: UUID | None = None
    prompt_version_id: UUID | None = None
    model_configuration_id: UUID | None = None
    metric_names: list[str] | None = Field(default=None, max_length=32)
    metric_options: dict[str, Any] | None = None


class EvaluationSuiteResponse(APIModel):
    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str | None
    dataset_version_id: UUID | None
    prompt_version_id: UUID | None
    model_configuration_id: UUID | None
    metric_names: list[str]
    metric_options: dict[str, Any]


class DatasetCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)


class DatasetUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    tags: list[str] | None = Field(default=None, max_length=32)


class DatasetResponse(APIModel):
    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str | None
    tags: list[str]


class TestCaseInput(APIModel):
    input: Any
    expected_output: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=32)


class TestCaseResponse(APIModel):
    id: UUID
    dataset_version_id: UUID
    row_number: int
    input: Any
    expected_output: Any
    metadata: dict[str, Any]
    tags: list[str]


class DatasetVersionCreate(APIModel):
    test_cases: list[TestCaseInput] = Field(min_length=1, max_length=100_000)
    created_by: str | None = Field(default=None, max_length=200)


class DatasetVersionResponse(APIModel):
    id: UUID
    dataset_id: UUID
    version_number: int
    source_format: Literal["csv", "jsonl", "manual"]
    row_count: int
    schema_fields: list[str]
    content_hash: str
    created_by: str | None
    test_cases: list[TestCaseResponse] | None = None


class DatasetVersionPreviewResponse(APIModel):
    version: DatasetVersionResponse
    test_cases: list[TestCaseResponse]


class PromptTemplateCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)
    template: str = Field(min_length=1, max_length=100_000)
    created_by: str | None = Field(default=None, max_length=200)


class PromptTemplateUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    tags: list[str] | None = Field(default=None, max_length=32)


class PromptVersionCreate(APIModel):
    template: str = Field(min_length=1, max_length=100_000)
    created_by: str | None = Field(default=None, max_length=200)


class PromptVersionResponse(APIModel):
    id: UUID
    prompt_template_id: UUID
    version_number: int
    template: str
    variables: list[str]
    created_by: str | None


class PromptTemplateResponse(APIModel):
    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    description: str | None
    tags: list[str]
    versions: list[PromptVersionResponse] | None = None


class PromptValidationResponse(APIModel):
    prompt_version_id: UUID
    dataset_version_id: UUID
    valid: bool
    required_variables: list[str]
    dataset_fields: list[str]
    missing_variables_by_row: dict[int, list[str]]


class PromptComparisonResponse(APIModel):
    prompt_template_id: UUID
    base_version_id: UUID
    candidate_version_id: UUID
    base_variables: list[str]
    candidate_variables: list[str]
    changed_variables: list[str]
    unified_diff: str


SECRET_KEY_PARTS = ("api_key", "apikey", "access_token", "secret", "password", "credential")


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            normalized_key = key.lower().replace("-", "_")
            if any(part in normalized_key for part in SECRET_KEY_PARTS):
                raise ValueError("secret values must be configured through environment variables")
            _reject_secret_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _reject_secret_keys(nested_value)


def reject_secret_keys(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    for key in value:
        normalized_key = key.lower().replace("-", "_")
        if any(part in normalized_key for part in SECRET_KEY_PARTS):
            raise ValueError("secret values must be configured through environment variables")
    _reject_secret_keys(value)
    return value


class ModelConfigurationCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=1, max_length=200)
    temperature: Decimal = Field(default=Decimal("0"), ge=0, le=2)
    max_tokens: int = Field(default=256, ge=1, le=1_000_000)
    timeout_seconds: int = Field(default=30, ge=1, le=3_600)
    parameters: dict[str, Any] = Field(default_factory=dict)

    _validate_parameters = field_validator("parameters")(reject_secret_keys)


class ModelConfigurationUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    temperature: Decimal | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=3_600)
    parameters: dict[str, Any] | None = None

    _validate_parameters = field_validator("parameters")(reject_secret_keys)


class ModelConfigurationResponse(APIModel):
    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    provider: str
    model_name: str
    temperature: Decimal
    max_tokens: int
    timeout_seconds: int
    parameters: dict[str, Any]


class ModelProviderResponse(APIModel):
    name: str
    configured: bool


class EvaluationRunCreate(APIModel):
    dataset_version_id: UUID
    prompt_version_id: UUID
    model_configuration_id: UUID
    suite_id: UUID | None = None
    requested_by: str | None = Field(default=None, max_length=200)
    metrics: list[str] | None = None
    metric_options: dict[str, Any] = Field(default_factory=dict)


class SuiteRunCreate(APIModel):
    requested_by: str | None = Field(default=None, max_length=200)
    metrics: list[str] | None = None
    metric_options: dict[str, Any] | None = None


class EvaluationAggregateResponse(APIModel):
    scope_type: str
    scope_key: str
    metric_name: str
    value: Decimal | None
    sample_count: int
    status: str
    details: dict[str, Any]


class EvaluationRunResponse(APIModel):
    id: UUID
    workspace_id: UUID
    suite_id: UUID | None
    dataset_version_id: UUID
    prompt_version_id: UUID
    model_configuration_id: UUID
    status: str
    requested_by: str | None
    failure_reason: str | None
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancel_requested_at: datetime | None
    total_cases: int
    completed_cases: int
    failed_cases: int
    metric_names: list[str]
    aggregates: list[EvaluationAggregateResponse] = Field(default_factory=list)


class EvaluationResultResponse(APIModel):
    id: UUID
    run_id: UUID
    test_case_id: UUID
    output: dict[str, Any]
    status: str
    latency_ms: int | None
    token_usage: dict[str, Any]
    provider_trace_id: str | None
    error_type: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class MetricResultResponse(APIModel):
    id: UUID
    run_id: UUID
    test_case_id: UUID | None
    metric_name: str
    value: Decimal
    status: str
    details: dict[str, Any]


class ProviderPricingCreate(APIModel):
    provider: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=1, max_length=200)
    input_cost_per_1k: Decimal = Field(ge=0)
    output_cost_per_1k: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)
    effective_from: datetime
    effective_to: datetime | None = None


class ProviderPricingResponse(APIModel):
    id: UUID
    workspace_id: UUID
    provider: str
    model_name: str
    input_cost_per_1k: Decimal
    output_cost_per_1k: Decimal
    currency: str
    effective_from: datetime
    effective_to: datetime | None


class ProviderPricingUpdate(APIModel):
    input_cost_per_1k: Decimal | None = Field(default=None, ge=0)
    output_cost_per_1k: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    effective_to: datetime | None = None


REGRESSION_RULE_TYPES = (
    "minimum_overall_score",
    "maximum_score_decrease",
    "maximum_failed_cases",
    "maximum_p95_latency",
    "maximum_estimated_cost",
    "per_metric_threshold",
)


class RegressionRuleCreate(APIModel):
    rule_type: Literal[
        "minimum_overall_score",
        "maximum_score_decrease",
        "maximum_failed_cases",
        "maximum_p95_latency",
        "maximum_estimated_cost",
        "per_metric_threshold",
    ] = "per_metric_threshold"
    metric_name: str | None = Field(default=None, max_length=120)
    tag: str | None = Field(default=None, max_length=120)
    operator: Literal["<", "<=", ">", ">=", "="]
    threshold: Decimal


class RegressionRuleResponse(APIModel):
    id: UUID
    baseline_id: UUID
    rule_type: str
    metric_name: str | None
    tag: str | None
    operator: str
    threshold: Decimal


class BaselineCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    evaluation_run_id: UUID


class BaselineResponse(APIModel):
    id: UUID
    workspace_id: UUID
    name: str
    evaluation_run_id: UUID
    rules: list[RegressionRuleResponse] = Field(default_factory=list)


class RegressionViolationResponse(APIModel):
    rule_id: UUID | None
    rule_type: str | None
    metric_name: str | None
    tag: str | None
    baseline_value: Decimal | None
    candidate_value: Decimal | None
    threshold: Decimal | None
    message: str


class RegressionComparisonResponse(APIModel):
    baseline_id: UUID
    baseline_run_id: UUID
    candidate_run_id: UUID
    status: Literal["passed", "failed", "not_evaluable"]
    regression_detected: bool
    violations: list[RegressionViolationResponse] = Field(default_factory=list)
    evaluated_at: datetime
