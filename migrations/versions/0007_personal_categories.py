"""Shared defaults and isolated personal categories."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "b52dbbcd48dc"
branch_labels = None
depends_on = None

DEFAULTS = (
    ("Groceries", "Продукты", "EXPENSE"),
    ("Transport", "Транспорт", "EXPENSE"),
    ("Housing", "Жильё", "EXPENSE"),
    ("Health", "Здоровье", "EXPENSE"),
    ("Other", "Прочее", "EXPENSE"),
    ("Salary", "Зарплата", "INCOME"),
    ("Gifts", "Подарки", "INCOME"),
    ("Other", "Прочее", "INCOME"),
)


def detach_transactions():
    # Пересоздаём дочернюю таблицу без ссылки на categories, сохраняя все данные.
    # Это позволяет менять categories при включённых внешних ключах SQLite.
    with op.batch_alter_table("transactions", naming_convention={
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    }) as batch:
        batch.drop_constraint("fk_transactions_category_id_categories", type_="foreignkey")


def attach_transactions():
    with op.batch_alter_table("transactions") as batch:
        batch.create_foreign_key("fk_transactions_category_id_categories", "categories", ["category_id"], ["id"])


def upgrade():
    detach_transactions()
    with op.batch_alter_table("categories") as batch:
        batch.drop_constraint("uq_category_type_name_en", type_="unique")
        batch.drop_constraint("uq_category_type_name_ru", type_="unique")
        batch.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_categories_user_id_users", "users", ["user_id"], ["id"])
        batch.create_index("ix_categories_user_id", ["user_id"])
        for name in ("name_en", "name_ru"):
            batch.create_index(f"uq_category_default_type_{name}", ["type", name], unique=True,
                               sqlite_where=sa.text("user_id IS NULL"))
            batch.create_index(f"uq_category_user_type_{name}", ["user_id", "type", name], unique=True,
                               sqlite_where=sa.text("user_id IS NOT NULL"))
    attach_transactions()
    connection = op.get_bind()
    categories = sa.table("categories", sa.column("name_en", sa.String()),
                          sa.column("name_ru", sa.String()), sa.column("type", sa.String()))
    for name_en, name_ru, kind in DEFAULTS:
        # Старые категории остаются общими; совпадающие названия не дублируем.
        exists = connection.execute(sa.select(categories.c.name_en).where(
            categories.c.type == kind,
            sa.or_(categories.c.name_en == name_en, categories.c.name_ru == name_ru),
        )).first()
        if exists is None:
            connection.execute(categories.insert().values(name_en=name_en, name_ru=name_ru, type=kind))


def downgrade():
    connection = op.get_bind()
    # Старая схема не поддерживает одинаковые имена у разных владельцев.
    for name in ("name_en", "name_ru"):
        if connection.execute(sa.text(
            f"SELECT 1 FROM categories GROUP BY type, {name} HAVING count(*) > 1 LIMIT 1"
        )).first():
            raise RuntimeError("Откат невозможен: названия категорий разных владельцев совпадают")
    detach_transactions()
    with op.batch_alter_table("categories") as batch:
        for name in ("name_en", "name_ru"):
            batch.drop_index(f"uq_category_default_type_{name}")
            batch.drop_index(f"uq_category_user_type_{name}")
        batch.drop_index("ix_categories_user_id")
        batch.drop_constraint("fk_categories_user_id_users", type_="foreignkey")
        batch.drop_column("user_id")
        batch.create_unique_constraint("uq_category_type_name_en", ["type", "name_en"])
        batch.create_unique_constraint("uq_category_type_name_ru", ["type", "name_ru"])
    attach_transactions()
