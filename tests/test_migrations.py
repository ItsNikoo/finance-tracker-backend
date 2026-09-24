from pathlib import Path
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect

from app.database import enable_foreign_keys


# Проверяет полный цикл первой миграции на отдельной базе.
class MigrationTests(unittest.TestCase):
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
                    {"categories", "transactions", "users", "alembic_version"},
                )
                command.check(config)
                command.downgrade(config, "base")
                self.assertEqual(inspect(connection).get_table_names(), ["alembic_version"])
                command.upgrade(config, "head")
                command.check(config)
        finally:
            engine.dispose()
