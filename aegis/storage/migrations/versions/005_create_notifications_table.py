"""Create notifications table

Revision ID: 005_create_notifications_table
Revises: 004_create_eligibility_and_match_scores
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_create_notifications_table"
down_revision: str | None = "004_create_eligibility_and_match_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.String(length=32),
            nullable=False,
            comment="email | telegram | in_app",
        ),
        sa.Column(
            "notification_type",
            sa.String(length=32),
            nullable=False,
            comment="immediate | digest",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=64),
            nullable=False,
            comment="SHA256(user_id + opportunity_id + version_hash)",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="pending | sent | failed",
        ),
        sa.Column(
            "content",
            sa.JSON(),
            nullable=False,
            server_default="{}",
            comment="Rendered notification content",
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Scheduled delivery timestamp (quiet hours deferral)",
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when actually sent",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_notification_idempotency_key"),
    )

    op.create_index(
        "ix_notifications_profile_id",
        "notifications",
        ["profile_id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_opportunity_id",
        "notifications",
        ["opportunity_id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_idempotency_key",
        "notifications",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_notifications_status",
        "notifications",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_profile_status",
        "notifications",
        ["profile_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_profile_status", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_idempotency_key", table_name="notifications")
    op.drop_index("ix_notifications_opportunity_id", table_name="notifications")
    op.drop_index("ix_notifications_profile_id", table_name="notifications")
    op.drop_table("notifications")
