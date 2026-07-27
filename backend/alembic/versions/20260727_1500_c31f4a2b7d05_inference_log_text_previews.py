"""inference log text previews

Revision ID: c31f4a2b7d05
Revises: b246520ac64d
Create Date: 2026-07-27 15:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c31f4a2b7d05'
down_revision: str | None = 'b246520ac64d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows so the NOT NULL can be added in one step.
    op.add_column('inference_logs', sa.Column('input_text', sa.Text(), server_default='', nullable=False))
    op.add_column('inference_logs', sa.Column('output_text', sa.Text(), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('inference_logs', 'output_text')
    op.drop_column('inference_logs', 'input_text')
