"""add topic_search to channels

Revision ID: 8d2f5c3f9b11
Revises: 15766a843b39
Create Date: 2026-05-05 08:55:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8d2f5c3f9b11"
down_revision: Union[str, None] = "15766a843b39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("topic_search", sa.String(length=512), nullable=True))
    op.create_index(op.f("ix_channels_topic_search"), "channels", ["topic_search"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_channels_topic_search"), table_name="channels")
    op.drop_column("channels", "topic_search")
