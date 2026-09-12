"""Create profiles table

Revision ID: 002_create_profiles_table
Revises: 001_initial_pgvector
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_create_profiles_table"
down_revision: str | None = "001_initial_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("education_level", sa.String(length=100), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("branch", sa.String(length=150), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("preferred_locations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("opportunity_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("interests", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("constraints", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("resume_raw_text", sa.Text(), nullable=True),
        sa.Column(
            "resume_extracted",
            sa.JSON(),
            nullable=True,
            comment="Draft extracted fields awaiting user confirmation",
        ),
        sa.Column(
            "resume_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Must be True for extracted fields to be authoritative",
        ),
        sa.Column(
            "resume_evidence",
            sa.JSON(),
            nullable=True,
            comment="Source text snippets and confidence scores per field",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")
