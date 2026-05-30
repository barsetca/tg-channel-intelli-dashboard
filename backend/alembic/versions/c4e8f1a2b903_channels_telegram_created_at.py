"""channels: telegram_created_at

Revision ID: c4e8f1a2b903
Revises: 8d2f5c3f9b11
Create Date: 2026-05-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8f1a2b903"
down_revision: str | None = "9b1a2c7d4e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "channels",
        sa.Column("telegram_created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("channels", "telegram_created_at")
