import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from app.database import enable_foreign_keys, get_db


# Проверяет API на изолированной базе в памяти.
class CategoryTests(unittest.IsolatedAsyncioTestCase):
    # Запускает приложение с пустой тестовой базой.
    async def asyncSetUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        event.listen(self.engine, "connect", enable_foreign_keys)
        self.sessions = sessionmaker(bind=self.engine)
        self.engine_patch = patch.object(main, "engine", self.engine)
        self.engine_patch.start()
        main.app.dependency_overrides[get_db] = self.get_test_db
        self.lifespan = main.app.router.lifespan_context(main.app)
        await self.lifespan.__aenter__()

    # Закрывает тестовую базу и восстанавливает зависимости.
    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        main.app.dependency_overrides.clear()
        self.engine_patch.stop()
        self.engine.dispose()

    # Выдаёт отдельную сессию тестовому запросу.
    def get_test_db(self):
        with self.sessions() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    # Выполняет HTTP-запрос через ASGI без внешнего клиента.
    async def request(self, method, path, data=None):
        messages = []
        body = json.dumps(data).encode() if data is not None else b""

        # Передаёт тело запроса приложению.
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        # Собирает сообщения HTTP-ответа.
        async def send(message):
            messages.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234), "server": ("test", 80),
        }
        await main.app(scope, receive, send)
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        result = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, json.loads(result)

    # Проверяет создание, чтение и уникальность обоих названий.
    async def test_categories(self):
        self.assertEqual(await self.request("GET", "/categories"), (200, []))
        data = {"name_en": " Other ", "name_ru": " Прочее ", "type": "income"}
        status, category = await self.request("POST", "/categories", data)
        self.assertEqual(status, 201)
        self.assertEqual(category["name_en"], "Other")
        self.assertEqual(category["name_ru"], "Прочее")
        self.assertEqual(await self.request("GET", f'/categories/{category["id"]}'), (200, category))
        for duplicate in (data, {**data, "name_en": "Different"}, {**data, "name_ru": "Другое"}):
            status, _ = await self.request("POST", "/categories", duplicate)
            self.assertEqual(status, 409)
        status, _ = await self.request("POST", "/categories", {**data, "type": "expense"})
        self.assertEqual(status, 201)
        status, categories = await self.request("GET", "/categories")
        self.assertEqual(len(categories), 2)
        status, _ = await self.request("GET", "/categories/999")
        self.assertEqual(status, 404)

    # Проверяет обязательность и допустимые значения полей категории.
    async def test_invalid_categories(self):
        valid = {"name_en": "Salary", "name_ru": "Зарплата", "type": "income"}
        for data in ({}, {**valid, "name_en": " "}, {**valid, "name_ru": ""},
                     {**valid, "name_en": "a" * 101}, {**valid, "type": "unknown"}):
            status, _ = await self.request("POST", "/categories", data)
            self.assertEqual(status, 422)

    # Проверяет связь транзакции с категорией и совпадение типов.
    async def test_transactions(self):
        for kind in ("income", "expense"):
            _, category = await self.request("POST", "/categories", {
                "name_en": "Other", "name_ru": "Прочее", "type": kind,
            })
            data = {"type": kind, "amount": "12.34", "category_id": category["id"]}
            status, transaction = await self.request("POST", "/transactions", data)
            self.assertEqual(status, 200)
            self.assertEqual(transaction["category_id"], category["id"])
            self.assertEqual(await self.request("GET", f'/transactions/{transaction["id"]}'), (200, transaction))
            opposite = "expense" if kind == "income" else "income"
            status, _ = await self.request("POST", "/transactions", {**data, "type": opposite})
            self.assertEqual(status, 400)
        status, transactions = await self.request("GET", "/transactions")
        self.assertEqual(len(transactions), 2)
        status, _ = await self.request("POST", "/transactions", {"type": "income", "amount": "1"})
        self.assertEqual(status, 422)
        status, _ = await self.request("POST", "/transactions", {**data, "category_id": 999})
        self.assertEqual(status, 404)

    # Проверяет ограничения БД при обходе API.
    async def test_database_constraints(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO categories (name_en, name_ru, type) VALUES ('Other', 'Прочее', 'INCOME')")
            for statement in (
                "INSERT INTO categories (name_en, name_ru, type) VALUES ('Other', 'Другое', 'INCOME')",
                "INSERT INTO categories (name_en, name_ru, type) VALUES ('Different', 'Прочее', 'INCOME')",
                "INSERT INTO transactions (type, amount, created_at) VALUES ('INCOME', 1, CURRENT_TIMESTAMP)",
                "INSERT INTO transactions (type, amount, created_at, category_id) VALUES ('INCOME', 1, CURRENT_TIMESTAMP, 999)",
            ):
                with self.assertRaises(IntegrityError):
                    connection.exec_driver_sql(statement)


if __name__ == "__main__":
    unittest.main()
