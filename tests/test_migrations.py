from pathlib import Path
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect

from app.database import enable_foreign_keys


# Проверяет полный цикл первой миграции на отдельной базе.
class MigrationTests(unittest.TestCase):
    # Проверяет перенос старой транзакции и сохранение данных при откате.
    def test_transaction_owner_backfill(self):
        engine = create_engine("sqlite://")
        event.listen(engine, "connect", enable_foreign_keys)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        try:
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "0002")
                connection.exec_driver_sql("INSERT INTO categories (id, name_en, name_ru, type) VALUES (1, 'Salary', 'Зарплата', 'INCOME')")
                connection.exec_driver_sql("INSERT INTO transactions (id, category_id, type, amount, created_at) VALUES (1, 1, 'INCOME', 42, '2026-09-25')")
                with self.assertRaisesRegex(RuntimeError, 'id = 1'):
                    command.upgrade(config, "head")
                self.assertNotIn("user_id", {c["name"] for c in inspect(connection).get_columns("transactions")})
                connection.exec_driver_sql("INSERT INTO users (id, email, hashed_password, created_at) VALUES (1, 'owner@example.com', 'test-only', '2026-09-25')")
                command.upgrade(config, "head")
                self.assertEqual(connection.exec_driver_sql("SELECT user_id, amount FROM transactions").one(), (1, 42))
                column = next(c for c in inspect(connection).get_columns("transactions") if c["name"] == "user_id")
                self.assertFalse(column["nullable"])
                self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_key_check").all(), [])
                command.check(config)
                command.downgrade(config, "0002")
                self.assertEqual(connection.exec_driver_sql("SELECT amount FROM transactions").scalar(), 42)
        finally:
            engine.dispose()

    # Создаёт таблицы, проверяет модели и откатывает схему.
    def test_upgrade_and_downgrade(self):
        engine = create_engine("sqlite://")
        event.listen(engine, "connect", enable_foreign_keys)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        try:
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                self.assertEqual(
                    set(inspect(connection).get_table_names()),
                    {"categories", "transactions", "users", "user_sessions", "alembic_version"},
                )
                command.check(config)
                command.downgrade(config, "base")
                self.assertEqual(inspect(connection).get_table_names(), ["alembic_version"])
                command.upgrade(config, "head")
                command.check(config)
        finally:
            engine.dispose()
