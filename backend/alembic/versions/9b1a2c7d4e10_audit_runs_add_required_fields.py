"""audit_runs add action/input/output/error/duration

Revision ID: 9b1a2c7d4e10
Revises: 8d2f5c3f9b11
Create Date: 2026-05-07 15:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b1a2c7d4e10"
down_revision: Union[str, None] = "8d2f5c3f9b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("audit_runs", sa.Column("action", sa.String(length=128), nullable=True))
    op.add_column("audit_runs", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("audit_runs", sa.Column("input_json", sa.JSON(), nullable=True))
    op.add_column("audit_runs", sa.Column("output_json", sa.JSON(), nullable=True))
    op.add_column("audit_runs", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_runs", "error")
    op.drop_column("audit_runs", "output_json")
    op.drop_column("audit_runs", "input_json")
    op.drop_column("audit_runs", "duration_ms")
    op.drop_column("audit_runs", "action")
