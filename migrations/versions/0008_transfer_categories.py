"""Add shared transfer categories for income and expenses."""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for kind in ("INCOME", "EXPENSE"):
        connection.execute(sa.text(
            "INSERT INTO categories (name_en, name_ru, type, user_id) "
            "SELECT :name_en, :name_ru, :kind, NULL WHERE NOT EXISTS ("
            "SELECT 1 FROM categories WHERE user_id IS NULL AND type = :kind "
            "AND (name_en = :name_en OR name_ru = :name_ru))"
        ), {"name_en": "Transfer", "name_ru": "Перевод", "kind": kind})


def downgrade():
    # Сохраняем категории и связанные операции при откате версии схемы.
    pass
