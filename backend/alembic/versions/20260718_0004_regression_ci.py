"""Add executable suite configuration and typed regression rules."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0004"
down_revision: str | None = "20260718_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_default(value: str) -> sa.TextClause:
    return sa.text(f"'{value}'::jsonb")


def upgrade() -> None:
    op.add_column(
        "evaluation_suites",
        sa.Column(
            "dataset_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dataset_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "evaluation_suites",
        sa.Column(
            "prompt_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "evaluation_suites",
        sa.Column(
            "model_configuration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_configurations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "evaluation_suites",
        sa.Column(
            "metric_names",
            postgresql.JSONB(),
            server_default=_json_default("[]"),
            nullable=False,
        ),
    )
    op.add_column(
        "evaluation_suites",
        sa.Column(
            "metric_options",
            postgresql.JSONB(),
            server_default=_json_default("{}"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_evaluation_suites_dataset_version_id", "evaluation_suites", ["dataset_version_id"]
    )
    op.create_index(
        "ix_evaluation_suites_prompt_version_id", "evaluation_suites", ["prompt_version_id"]
    )
    op.create_index(
        "ix_evaluation_suites_model_configuration_id",
        "evaluation_suites",
        ["model_configuration_id"],
    )

    op.add_column(
        "regression_rules",
        sa.Column(
            "rule_type",
            sa.String(length=60),
            server_default="per_metric_threshold",
            nullable=False,
        ),
    )
    op.alter_column("regression_rules", "metric_name", existing_type=sa.String(120), nullable=True)
    op.add_column("regression_rules", sa.Column("tag", sa.String(length=120), nullable=True))
    op.execute(
        sa.text(
            "UPDATE evaluation_suites "
            "SET dataset_version_id = :dataset_version_id, "
            "prompt_version_id = :prompt_version_id, "
            "model_configuration_id = :model_configuration_id, "
            "metric_names = CAST(:metric_names AS jsonb) "
            "WHERE id = :suite_id"
        ).bindparams(
            dataset_version_id="00000000-0000-0000-0000-000000000004",
            prompt_version_id="00000000-0000-0000-0000-000000000008",
            model_configuration_id="00000000-0000-0000-0000-000000000009",
            metric_names='["exact_match", "latency_ms"]',
            suite_id="00000000-0000-0000-0000-000000000002",
        )
    )


def downgrade() -> None:
    op.drop_column("regression_rules", "tag")
    op.alter_column("regression_rules", "metric_name", existing_type=sa.String(120), nullable=False)
    op.drop_column("regression_rules", "rule_type")
    op.drop_index("ix_evaluation_suites_model_configuration_id", table_name="evaluation_suites")
    op.drop_index("ix_evaluation_suites_prompt_version_id", table_name="evaluation_suites")
    op.drop_index("ix_evaluation_suites_dataset_version_id", table_name="evaluation_suites")
    for name in (
        "metric_options",
        "metric_names",
        "model_configuration_id",
        "prompt_version_id",
        "dataset_version_id",
    ):
        op.drop_column("evaluation_suites", name)
