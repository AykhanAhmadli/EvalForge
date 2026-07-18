from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from evalforge.enums import EvaluationItemStatus, EvaluationRunStatus, JobStatus


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Dataset(Base, TimestampMixin):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("name", name="uq_datasets_name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    rows: Mapped[list[DatasetRow]] = relationship(back_populates="dataset", cascade="all, delete")


class DatasetRow(Base, TimestampMixin):
    __tablename__ = "dataset_rows"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "ordinal", "version", name="uq_dataset_rows_position_version"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    row_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    dataset: Mapped[Dataset] = relationship(back_populates="rows")


class PromptConfig(Base, TimestampMixin):
    __tablename__ = "prompt_configs"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_configs_name_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_configs_name_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class MetricDefinitionRecord(Base, TimestampMixin):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_metrics_name_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    semantics: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EvaluationRun(Base, TimestampMixin):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"))
    prompt_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_configs.id", ondelete="RESTRICT")
    )
    model_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_configs.id", ondelete="RESTRICT")
    )
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=EvaluationRunStatus.draft.value,
        nullable=False,
        index=True,
    )
    requested_by: Mapped[str | None] = mapped_column(String(200))
    failure_reason: Mapped[str | None] = mapped_column(Text)


class EvaluationItem(Base, TimestampMixin):
    __tablename__ = "evaluation_items"
    __table_args__ = (
        UniqueConstraint("run_id", "dataset_row_id", name="uq_evaluation_items_run_row"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"))
    dataset_row_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_rows.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=EvaluationItemStatus.pending.value,
        nullable=False,
    )
    rendered_prompt_hash: Mapped[str | None] = mapped_column(String(128))


class EvaluationResult(Base, TimestampMixin):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_items.id", ondelete="CASCADE")
    )
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    provider_trace_id: Mapped[str | None] = mapped_column(String(200))


class MetricResult(Base, TimestampMixin):
    __tablename__ = "metric_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluation_items.id", ondelete="CASCADE")
    )
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class EvaluationComparison(Base, TimestampMixin):
    __tablename__ = "evaluation_comparisons"

    id: Mapped[uuid.UUID] = uuid_pk()
    baseline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE")
    )
    candidate_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE")
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    regression_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Job(Base, TimestampMixin):
    __tablename__ = "job_queue"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=JobStatus.queued.value,
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    locked_by: Mapped[str | None] = mapped_column(String(200))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
