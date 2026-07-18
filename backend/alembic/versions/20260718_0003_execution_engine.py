"""Add evaluation execution lifecycle, pricing, and aggregate snapshots."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0003"
down_revision: str | None = "20260718_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_default(value: str) -> sa.TextClause:
    return sa.text(f"'{value}'::jsonb")


def upgrade() -> None:
    run_columns = [
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_cases", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "metric_names", postgresql.JSONB(), server_default=_json_default("[]"), nullable=False
        ),
        sa.Column(
            "metric_options", postgresql.JSONB(), server_default=_json_default("{}"), nullable=False
        ),
    ]
    for column in run_columns:
        op.add_column("managed_evaluation_runs", column)

    result_columns = [
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in result_columns:
        op.add_column("managed_evaluation_results", column)
    op.add_column(
        "managed_metric_results",
        sa.Column("status", sa.String(length=32), server_default="valid", nullable=False),
    )

    job_columns = [
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_type", sa.String(length=120), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in job_columns:
        op.add_column("job_queue", column)

    op.create_table(
        "provider_pricing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("input_cost_per_1k", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("output_cost_per_1k", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            "model_name",
            "effective_from",
            name="uq_provider_pricing_effective",
        ),
    )
    op.create_index("ix_provider_pricing_workspace_id", "provider_pricing", ["workspace_id"])

    op.create_table(
        "run_aggregates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=40), nullable=False),
        sa.Column("scope_key", sa.String(length=200), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="valid", nullable=False),
        sa.Column(
            "details", postgresql.JSONB(), server_default=_json_default("{}"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["managed_evaluation_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "run_id",
            "scope_type",
            "scope_key",
            "metric_name",
            name="uq_run_aggregates_scope_metric",
        ),
    )
    op.create_index("ix_run_aggregates_run_id", "run_aggregates", ["run_id"])

    op.bulk_insert(
        sa.table(
            "provider_pricing",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
            sa.column("provider", sa.String()),
            sa.column("model_name", sa.String()),
            sa.column("input_cost_per_1k", sa.Numeric()),
            sa.column("output_cost_per_1k", sa.Numeric()),
            sa.column("currency", sa.String()),
            sa.column("effective_from", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "workspace_id": "00000000-0000-0000-0000-000000000001",
                "provider": "fake",
                "model_name": "evalforge-fake-v1",
                "input_cost_per_1k": 0,
                "output_cost_per_1k": 0,
                "currency": "USD",
                "effective_from": "2026-01-01T00:00:00+00:00",
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_run_aggregates_run_id", table_name="run_aggregates")
    op.drop_table("run_aggregates")
    op.drop_index("ix_provider_pricing_workspace_id", table_name="provider_pricing")
    op.drop_table("provider_pricing")
    for name in ("failed_at", "completed_at", "last_error_type", "lease_expires_at"):
        op.drop_column("job_queue", name)
    op.drop_column("managed_metric_results", "status")
    for name in ("completed_at", "started_at", "error_message", "error_type", "status"):
        op.drop_column("managed_evaluation_results", name)
    for name in (
        "metric_options",
        "metric_names",
        "failed_cases",
        "completed_cases",
        "total_cases",
        "cancel_requested_at",
        "cancelled_at",
        "completed_at",
        "started_at",
        "queued_at",
    ):
        op.drop_column("managed_evaluation_runs", name)
