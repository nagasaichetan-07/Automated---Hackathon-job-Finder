"""Create eligibility_decisions and match_scores tables

Revision ID: 004_create_eligibility_and_match_scores
Revises: 003_create_sources_and_connectors
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_create_eligibility_and_match_scores"
down_revision: str | None = "003_create_sources_and_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Eligibility Decisions table
    op.create_table(
        "eligibility_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=50), nullable=False, comment="ELIGIBLE, INELIGIBLE, UNKNOWN"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rule_results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("opportunity_id", "profile_id", name="uq_eligibility_opportunity_profile"),
    )
    op.create_index("ix_eligibility_decisions_opportunity_id", "eligibility_decisions", ["opportunity_id"])
    op.create_index("ix_eligibility_decisions_profile_id", "eligibility_decisions", ["profile_id"])
    op.create_index("ix_eligibility_decisions_state", "eligibility_decisions", ["state"])

    # 2. Match Scores table
    op.create_table(
        "match_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("eligibility_score", sa.Float(), nullable=False),
        sa.Column("feature_overlap_score", sa.Float(), nullable=False),
        sa.Column("semantic_similarity_score", sa.Float(), nullable=False),
        sa.Column("weights_used", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("score_breakdown", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("user_feedback", sa.String(length=50), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("opportunity_id", "profile_id", name="uq_match_opportunity_profile"),
    )
    op.create_index("ix_match_scores_opportunity_id", "match_scores", ["opportunity_id"])
    op.create_index("ix_match_scores_profile_id", "match_scores", ["profile_id"])
    op.create_index("ix_match_scores_final_score", "match_scores", ["final_score"])


def downgrade() -> None:
    op.drop_index("ix_match_scores_final_score", table_name="match_scores")
    op.drop_index("ix_match_scores_profile_id", table_name="match_scores")
    op.drop_index("ix_match_scores_opportunity_id", table_name="match_scores")
    op.drop_table("match_scores")

    op.drop_index("ix_eligibility_decisions_state", table_name="eligibility_decisions")
    op.drop_index("ix_eligibility_decisions_profile_id", table_name="eligibility_decisions")
    op.drop_index("ix_eligibility_decisions_opportunity_id", table_name="eligibility_decisions")
    op.drop_table("eligibility_decisions")
