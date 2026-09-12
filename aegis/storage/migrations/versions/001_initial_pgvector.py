"""Initial migration enabling pgvector extension

Revision ID: 001_initial_pgvector
Revises:
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_pgvector"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgvector extension if on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP EXTENSION IF EXISTS vector CASCADE;")
