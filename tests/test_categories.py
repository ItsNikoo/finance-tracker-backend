import json
import unittest
from unittest.mock import patch
from pathlib import Path

from alembic import command
from alembic.config import Config

from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from app.database import enable_foreign_keys, get_db
from app.models.user import User
from app.repository.user_repository import UserRepository
from app.security import password_hasher


# Проверяет API на изолированной базе в памяти.
class CategoryTests(unittest.IsolatedAsyncioTestCase):
    # Запускает приложение с пустой тестовой базой.
    async def asyncSetUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        event.listen(self.engine, "connect", enable_foreign_keys)
        self.sessions = sessionmaker(bind=self.engine)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        main.app.dependency_overrides[get_db] = self.get_test_db
        self.lifespan = main.app.router.lifespan_context(main.app)
        await self.lifespan.__aenter__()

    # Закрывает тестовую базу и восстанавливает зависимости.
    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        main.app.dependency_overrides.clear()
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
        self.assertEqual(await self.request("GET", "/api/categories"), (200, []))
        data = {"name_en": " Other ", "name_ru": " Прочее ", "type": "income"}
        status, category = await self.request("POST", "/api/categories", data)
        self.assertEqual(status, 201)
        self.assertEqual(category["name_en"], "Other")
        self.assertEqual(category["name_ru"], "Прочее")
        self.assertEqual(await self.request("GET", f'/api/categories/{category["id"]}'), (200, category))
        for duplicate in (data, {**data, "name_en": "Different"}, {**data, "name_ru": "Другое"}):
            status, _ = await self.request("POST", "/api/categories", duplicate)
            self.assertEqual(status, 409)
        status, _ = await self.request("POST", "/api/categories", {**data, "type": "expense"})
        self.assertEqual(status, 201)
        status, categories = await self.request("GET", "/api/categories")
        self.assertEqual(len(categories), 2)
        status, _ = await self.request("GET", "/api/categories/999")
        self.assertEqual(status, 404)

    # Проверяет обязательность и допустимые значения полей категории.
    async def test_invalid_categories(self):
        valid = {"name_en": "Salary", "name_ru": "Зарплата", "type": "income"}
        for data in ({}, {**valid, "name_en": " "}, {**valid, "name_ru": ""},
                     {**valid, "name_en": "a" * 101}, {**valid, "type": "unknown"}):
            status, _ = await self.request("POST", "/api/categories", data)
            self.assertEqual(status, 422)

    # Проверяет связь транзакции с категорией и совпадение типов.
    async def test_transactions(self):
        for kind in ("income", "expense"):
            _, category = await self.request("POST", "/api/categories", {
                "name_en": "Other", "name_ru": "Прочее", "type": kind,
            })
            data = {"type": kind, "amount": "12.34", "category_id": category["id"]}
            status, transaction = await self.request("POST", "/api/transactions", data)
            self.assertEqual(status, 200)
            self.assertEqual(transaction["category_id"], category["id"])
            self.assertEqual(await self.request("GET", f'/api/transactions/{transaction["id"]}'), (200, transaction))
            opposite = "expense" if kind == "income" else "income"
            status, _ = await self.request("POST", "/api/transactions", {**data, "type": opposite})
            self.assertEqual(status, 400)
        status, transactions = await self.request("GET", "/api/transactions")
        self.assertEqual(len(transactions), 2)
        status, _ = await self.request("POST", "/api/transactions", {"type": "income", "amount": "1"})
        self.assertEqual(status, 422)
        status, _ = await self.request("POST", "/api/transactions", {**data, "category_id": 999})
        self.assertEqual(status, 404)

    # Проверяет регистрацию, хеширование и публичный ответ.
    async def test_user_creation(self):
        password = "Example-password-123"
        status, data = await self.request("POST", "/api/users/create", {
            "email": " Alice@Example.com ", "password": password,
        })
        self.assertEqual(status, 201)
        self.assertEqual(set(data), {"id", "email", "created_at"})
        self.assertEqual(data["email"], "alice@example.com")
        self.assertTrue(data["created_at"])
        with self.sessions() as db:
            user = db.get(User, data["id"])
            self.assertNotEqual(user.hashed_password, password)
            self.assertTrue(password_hasher.verify(password, user.hashed_password))
            self.assertFalse(password_hasher.verify("wrong-password", user.hashed_password))
            self.assertIsNotNone(user.created_at)
        status, _ = await self.request("POST", "/api/users/create", {
            "email": "ALICE@example.com", "password": password,
        })
        self.assertEqual(status, 409)

    # Проверяет формат email и ограничения пароля.
    async def test_invalid_users(self):
        for payload in (
            {"email": "invalid", "password": "Example-password-123"},
            {"email": "alice@example.com", "password": "short"},
            {"email": "alice@example.com", "password": "x" * 129},
            {"email": "alice@example.com"},
        ):
            status, _ = await self.request("POST", "/api/users/create", payload)
            self.assertEqual(status, 422)

    # Проверяет конфликт после предварительной проверки email.
    async def test_user_unique_conflict(self):
        payload = {"email": "alice@example.com", "password": "Example-password-123"}
        status, data = await self.request("POST", "/api/users/create", payload)
        self.assertEqual(status, 201)
        with self.sessions() as db:
            existing = db.get(User, data["id"])
            with patch.object(UserRepository, "get_user_by_email", side_effect=[None, existing]):
                status, _ = await self.request("POST", "/api/users/create", payload)
            self.assertEqual(status, 409)
        status, _ = await self.request("POST", "/api/users/create", {
            **payload, "email": "bob@example.com",
        })
        self.assertEqual(status, 201)

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
