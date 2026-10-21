"""Add Moscow transaction occurrence date, preserving existing timestamps."""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("occurred_at", sa.DateTime(), nullable=True))
    # Старые даты не содержат timezone; сохраняем часы и трактуем их как МСК.
    op.execute("UPDATE transactions SET occurred_at = created_at")
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.alter_column("occurred_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.create_index("ix_transactions_user_occurred_at", ["user_id", "occurred_at"])


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_user_occurred_at")
        batch_op.drop_column("occurred_at")
