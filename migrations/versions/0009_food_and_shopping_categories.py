"""Separate groceries, cafes, delivery and shopping."""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Сохраняем ID прежней общей категории «Еда» и ссылки транзакций.
    connection.execute(sa.text(
        "UPDATE categories SET name_en = :name_en, name_ru = :name_ru "
        "WHERE user_id IS NULL AND type = 'EXPENSE' AND name_ru = :old_name "
        "AND NOT EXISTS (SELECT 1 FROM categories WHERE user_id IS NULL "
        "AND type = 'EXPENSE' AND (name_en = :name_en OR name_ru = :name_ru))"
    ), {"name_en": "Cafes and restaurants", "name_ru": "Кафе и рестораны", "old_name": "Еда"})
    for name_en, name_ru in (
        ("Groceries", "Продукты"),
        ("Cafes and restaurants", "Кафе и рестораны"),
        ("Delivery", "Доставка"),
        ("Shopping", "Шоппинг"),
    ):
        connection.execute(sa.text(
            "INSERT INTO categories (name_en, name_ru, type, user_id) "
            "SELECT :name_en, :name_ru, 'EXPENSE', NULL WHERE NOT EXISTS ("
            "SELECT 1 FROM categories WHERE user_id IS NULL AND type = 'EXPENSE' "
            "AND (name_en = :name_en OR name_ru = :name_ru))"
        ), {"name_en": name_en, "name_ru": name_ru})


def downgrade():
    # Изменения справочника сохраняются, чтобы не затрагивать историю операций.
    pass
