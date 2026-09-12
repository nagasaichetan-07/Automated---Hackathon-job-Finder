"""Create sources, raw_snapshots, source_runs, and opportunities tables

Revision ID: 003_create_sources_and_connectors
Revises: 002_create_profiles_table
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_create_sources_and_connectors"
down_revision: str | None = "002_create_profiles_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Sources table
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False, comment="api, web, or rss"),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("connector_class", sa.String(length=255), nullable=False),
        sa.Column("connector_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("cadence", sa.String(length=100), nullable=False, server_default="0 */6 * * *"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("health_state", sa.String(length=50), nullable=False, server_default="healthy"),
        sa.Column("access_notes", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sources_enabled", "sources", ["enabled"])

    # 2. Raw Snapshots table
    op.create_table(
        "raw_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "content_hash", name="uq_raw_snapshot_source_hash"),
    )
    op.create_index("ix_raw_snapshots_source_id", "raw_snapshots", ["source_id"])
    op.create_index("ix_raw_snapshots_content_hash", "raw_snapshots", ["content_hash"])

    # 3. Source Runs table
    op.create_table(
        "source_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_source_runs_source_id", "source_runs", ["source_id"])

    # 4. Opportunities table
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="job"),
        sa.Column("organizer", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("mode", sa.String(length=50), nullable=True),
        sa.Column("eligibility_text", sa.Text(), nullable=True),
        sa.Column("team_size_min", sa.Integer(), nullable=True),
        sa.Column("team_size_max", sa.Integer(), nullable=True),
        sa.Column("prize", sa.String(length=255), nullable=True),
        sa.Column("skills_themes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "external_id", name="uq_opportunity_source_external"),
    )
    op.create_index("ix_opportunities_source_id", "opportunities", ["source_id"])
    op.create_index("ix_opportunities_external_id", "opportunities", ["external_id"])


def downgrade() -> None:
    op.drop_index("ix_opportunities_external_id", table_name="opportunities")
    op.drop_index("ix_opportunities_source_id", table_name="opportunities")
    op.drop_table("opportunities")

    op.drop_index("ix_source_runs_source_id", table_name="source_runs")
    op.drop_table("source_runs")

    op.drop_index("ix_raw_snapshots_content_hash", table_name="raw_snapshots")
    op.drop_index("ix_raw_snapshots_source_id", table_name="raw_snapshots")
    op.drop_table("raw_snapshots")

    op.drop_index("ix_sources_enabled", table_name="sources")
    op.drop_table("sources")
