"""Add dataset, prompt, model, and regression management tables."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260718_0002"
down_revision: str | None = "20260718_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )

    op.create_table(
        "evaluation_suites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_evaluation_suites_workspace_slug"),
    )
    op.create_index("ix_evaluation_suites_workspace_id", "evaluation_suites", ["workspace_id"])

    op.create_table(
        "managed_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_managed_datasets_workspace_slug"),
    )
    op.create_index("ix_managed_datasets_workspace_id", "managed_datasets", ["workspace_id"])

    op.create_table(
        "dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_format", sa.String(length=16), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("schema_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["managed_datasets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_versions_number"),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])

    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("dataset_version_id", "row_number", name="uq_test_cases_version_row"),
    )
    op.create_index("ix_test_cases_dataset_version_id", "test_cases", ["dataset_version_id"])

    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_prompt_templates_workspace_slug"),
    )
    op.create_index("ix_prompt_templates_workspace_id", "prompt_templates", ["workspace_id"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"], ["prompt_templates.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "prompt_template_id", "version_number", name="uq_prompt_versions_number"
        ),
    )
    op.create_index("ix_prompt_versions_template_id", "prompt_versions", ["prompt_template_id"])

    op.create_table(
        "model_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("temperature", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_model_configurations_workspace_slug"),
    )
    op.create_index(
        "ix_model_configurations_workspace_id", "model_configurations", ["workspace_id"]
    )

    op.create_table(
        "managed_evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_configuration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["model_configuration_id"], ["model_configurations.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_managed_evaluation_runs_workspace_id", "managed_evaluation_runs", ["workspace_id"]
    )
    op.create_index("ix_managed_evaluation_runs_status", "managed_evaluation_runs", ["status"])

    op.create_table(
        "managed_evaluation_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider_trace_id", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["managed_evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", "test_case_id", name="uq_managed_results_run_case"),
    )
    op.create_index(
        "ix_managed_evaluation_results_run_id", "managed_evaluation_results", ["run_id"]
    )
    op.create_index(
        "ix_managed_evaluation_results_test_case_id", "managed_evaluation_results", ["test_case_id"]
    )

    op.create_table(
        "managed_metric_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("test_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["managed_evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["test_case_id"], ["test_cases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "run_id", "test_case_id", "metric_name", name="uq_managed_metric_results_key"
        ),
    )
    op.create_index("ix_managed_metric_results_run_id", "managed_metric_results", ["run_id"])
    op.create_index(
        "ix_managed_metric_results_metric_name", "managed_metric_results", ["metric_name"]
    )

    op.create_table(
        "baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["managed_evaluation_runs.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_baselines_workspace_name"),
    )
    op.create_index("ix_baselines_workspace_id", "baselines", ["workspace_id"])

    op.create_table(
        "regression_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=12, scale=6), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["baseline_id"], ["baselines.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_regression_rules_baseline_id", "regression_rules", ["baseline_id"])

    seed_workspace = "00000000-0000-0000-0000-000000000001"
    seed_suite = "00000000-0000-0000-0000-000000000002"
    seed_dataset = "00000000-0000-0000-0000-000000000003"
    seed_dataset_version = "00000000-0000-0000-0000-000000000004"
    seed_case_one = "00000000-0000-0000-0000-000000000005"
    seed_case_two = "00000000-0000-0000-0000-000000000006"
    seed_prompt = "00000000-0000-0000-0000-000000000007"
    seed_prompt_version = "00000000-0000-0000-0000-000000000008"
    seed_model = "00000000-0000-0000-0000-000000000009"

    op.bulk_insert(
        sa.table(
            "workspaces",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("name", sa.String()),
            sa.column("slug", sa.String()),
            sa.column("description", sa.Text()),
        ),
        [
            {
                "id": seed_workspace,
                "name": "Local Workspace",
                "slug": "local",
                "description": "Seed workspace for local development.",
            }
        ],
    )
    op.bulk_insert(
        sa.table(
            "evaluation_suites",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
            sa.column("name", sa.String()),
            sa.column("slug", sa.String()),
            sa.column("description", sa.Text()),
        ),
        [
            {
                "id": seed_suite,
                "workspace_id": seed_workspace,
                "name": "Starter Evaluation",
                "slug": "starter",
                "description": "Small deterministic examples for local development.",
            }
        ],
    )
    op.execute(
        sa.text(
            "INSERT INTO managed_datasets "
            "(id, workspace_id, name, slug, description, tags) VALUES "
            "(:id, :workspace_id, 'Starter Questions', 'starter-questions', "
            "'Two examples used to verify the local management flow.', "
            '\'["demo","local"]\'::jsonb'
        ).bindparams(id=seed_dataset, workspace_id=seed_workspace)
    )
    op.execute(
        sa.text(
            "INSERT INTO dataset_versions "
            "(id, dataset_id, version_number, source_format, row_count, schema_fields, "
            "content_hash, created_by) VALUES "
            "(:id, :dataset_id, 1, 'jsonl', 2, '[\"question\"]'::jsonb, "
            "'df452a9b408c05f31e935d9dcbf173e80a50a313f5557c3519017d523c231db7', 'seed')"
        ).bindparams(id=seed_dataset_version, dataset_id=seed_dataset)
    )
    op.execute(
        sa.text(
            "INSERT INTO test_cases "
            "(id, dataset_version_id, row_number, input, expected_output, metadata, tags) VALUES "
            '(:case_one, :version_id, 1, \'{"question":"What is 2 + 2?"}\'::jsonb, '
            "'\"4\"'::jsonb, '{}'::jsonb, '[\"arithmetic\"]'::jsonb), "
            "(:case_two, :version_id, 2, "
            '\'{"question":"What is the capital of France?"}\'::jsonb, '
            "'\"Paris\"'::jsonb, '{}'::jsonb, '[\"facts\"]'::jsonb)"
        ).bindparams(
            case_one=seed_case_one,
            case_two=seed_case_two,
            version_id=seed_dataset_version,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO prompt_templates "
            "(id, workspace_id, name, slug, description, tags) VALUES "
            "(:id, :workspace_id, 'Answer the question', 'answer-question', "
            "'Simple prompt for the starter dataset.', '[\"demo\",\"local\"]'::jsonb"
        ).bindparams(id=seed_prompt, workspace_id=seed_workspace)
    )
    op.execute(
        sa.text(
            "INSERT INTO prompt_versions "
            "(id, prompt_template_id, version_number, template, variables, created_by) VALUES "
            "(:id, :template_id, 1, 'Answer this question briefly: {{ question }}', "
            "'[\"question\"]'::jsonb, 'seed'"
        ).bindparams(id=seed_prompt_version, template_id=seed_prompt)
    )
    op.execute(
        sa.text(
            "INSERT INTO model_configurations "
            "(id, workspace_id, name, slug, provider, model_name, temperature, max_tokens, "
            "timeout_seconds, parameters) VALUES "
            "(:id, :workspace_id, 'Deterministic Fake', 'deterministic-fake', 'fake', "
            "'evalforge-fake-v1', 0, 256, 30, '{}'::jsonb)"
        ).bindparams(id=seed_model, workspace_id=seed_workspace)
    )


def downgrade() -> None:
    op.drop_index("ix_regression_rules_baseline_id", table_name="regression_rules")
    op.drop_table("regression_rules")
    op.drop_index("ix_baselines_workspace_id", table_name="baselines")
    op.drop_table("baselines")
    op.drop_index("ix_managed_metric_results_metric_name", table_name="managed_metric_results")
    op.drop_index("ix_managed_metric_results_run_id", table_name="managed_metric_results")
    op.drop_table("managed_metric_results")
    op.drop_index(
        "ix_managed_evaluation_results_test_case_id", table_name="managed_evaluation_results"
    )
    op.drop_index("ix_managed_evaluation_results_run_id", table_name="managed_evaluation_results")
    op.drop_table("managed_evaluation_results")
    op.drop_index("ix_managed_evaluation_runs_status", table_name="managed_evaluation_runs")
    op.drop_index("ix_managed_evaluation_runs_workspace_id", table_name="managed_evaluation_runs")
    op.drop_table("managed_evaluation_runs")
    op.drop_index("ix_model_configurations_workspace_id", table_name="model_configurations")
    op.drop_table("model_configurations")
    op.drop_index("ix_prompt_versions_template_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompt_templates_workspace_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")
    op.drop_index("ix_test_cases_dataset_version_id", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index("ix_dataset_versions_dataset_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index("ix_managed_datasets_workspace_id", table_name="managed_datasets")
    op.drop_table("managed_datasets")
    op.drop_index("ix_evaluation_suites_workspace_id", table_name="evaluation_suites")
    op.drop_table("evaluation_suites")
    op.drop_table("workspaces")
