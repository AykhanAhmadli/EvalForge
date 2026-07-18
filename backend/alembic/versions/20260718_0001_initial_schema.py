"""Initial EvalForge schema."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", name="uq_datasets_name"),
    )

    op.create_table(
        "prompt_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", "version", name="uq_prompt_configs_name_version"),
    )

    op.create_table(
        "model_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", "version", name="uq_model_configs_name_version"),
    )

    op.create_table(
        "metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("semantics", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("name", "version", name="uq_metrics_name_version"),
    )

    op.create_table(
        "dataset_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "dataset_id", "ordinal", "version", name="uq_dataset_rows_position_version"
        ),
    )
    op.create_index("ix_dataset_rows_dataset_id", "dataset_rows", ["dataset_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_config_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["evaluation_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_config_id"], ["model_configs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prompt_config_id"], ["prompt_configs.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])

    op.create_table(
        "job_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(length=120), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("locked_by", sa.String(length=200), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_job_queue_claim", "job_queue", ["status", "run_after", "priority", "created_at"]
    )

    op.create_table(
        "evaluation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rendered_prompt_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["dataset_row_id"], ["dataset_rows.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "dataset_row_id", name="uq_evaluation_items_run_row"),
    )
    op.create_index("ix_evaluation_items_run_id", "evaluation_items", ["run_id"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_trace_id", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["item_id"], ["evaluation_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_results_item_id", "evaluation_results", ["item_id"])

    op.create_table(
        "metric_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["item_id"], ["evaluation_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_metric_results_run_id", "metric_results", ["run_id"])
    op.create_index("ix_metric_results_metric_name", "metric_results", ["metric_name"])

    op.create_table(
        "evaluation_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("baseline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("regression_detected", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_evaluation_comparisons_runs",
        "evaluation_comparisons",
        ["baseline_run_id", "candidate_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_comparisons_runs", table_name="evaluation_comparisons")
    op.drop_table("evaluation_comparisons")
    op.drop_index("ix_metric_results_metric_name", table_name="metric_results")
    op.drop_index("ix_metric_results_run_id", table_name="metric_results")
    op.drop_table("metric_results")
    op.drop_index("ix_evaluation_results_item_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_items_run_id", table_name="evaluation_items")
    op.drop_table("evaluation_items")
    op.drop_index("ix_job_queue_claim", table_name="job_queue")
    op.drop_table("job_queue")
    op.drop_index("ix_evaluation_runs_status", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_dataset_rows_dataset_id", table_name="dataset_rows")
    op.drop_table("dataset_rows")
    op.drop_table("metrics")
    op.drop_table("model_configs")
    op.drop_table("prompt_configs")
    op.drop_table("datasets")
