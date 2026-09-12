"""Create repair_runs and repair_patches tables

Revision ID: 006_create_repair_tables
Revises: 005_create_notifications_table
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_create_repair_tables"
down_revision: str | None = "005_create_notifications_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repair_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trigger_type",
            sa.String(length=50),
            nullable=False,
            server_default="automatic",
        ),
        sa.Column(
            "failure_class",
            sa.String(length=50),
            nullable=False,
            server_default="selector_not_found",
        ),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("outcome", sa.String(length=50), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_repair_runs_source_id", "repair_runs", ["source_id"], unique=False)

    op.create_table(
        "repair_patches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repair_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repair_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(length=50),
            nullable=False,
            server_default="PROPOSED",
        ),
        sa.Column("diff_content", sa.Text(), nullable=False),
        sa.Column("target_file", sa.String(length=255), nullable=False),
        sa.Column("test_results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("validation_results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sandbox_passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("connector_version_before", sa.Text(), nullable=True),
        sa.Column("connector_version_after", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "proposed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_repair_patches_repair_run_id", "repair_patches", ["repair_run_id"], unique=False)
    op.create_index("ix_repair_patches_state", "repair_patches", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_repair_patches_state", table_name="repair_patches")
    op.drop_index("ix_repair_patches_repair_run_id", table_name="repair_patches")
    op.drop_table("repair_patches")
    op.drop_index("ix_repair_runs_source_id", table_name="repair_runs")
    op.drop_table("repair_runs")
