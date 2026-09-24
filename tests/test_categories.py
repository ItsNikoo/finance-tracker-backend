import json
import os
import time
import jwt
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
    async def request(self, method, path, data=None, headers=None):
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
            "headers": [(b"content-type", b"application/json")] + (headers or []),
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

    # Проверяет выдачу подписанного токена и отказ при неверном пароле.
    async def test_user_login(self):
        credentials = {"email": "alice@example.com", "password": "Example-password-123"}
        status, user = await self.request("POST", "/api/users/create", credentials)
        self.assertEqual(status, 201)
        secret = "test-only-secret-key-with-at-least-32-bytes"
        with patch.dict(os.environ, {"JWT_SECRET_KEY": secret}):
            status, data = await self.request("POST", "/api/users/login", credentials)
            self.assertEqual(status, 200)
            self.assertEqual(set(data), {"access_token", "token_type"})
            self.assertEqual(data["token_type"], "bearer")
            claims = jwt.decode(data["access_token"], secret, algorithms=["HS256"])
            self.assertEqual(set(claims), {"sub", "iat", "exp"})
            self.assertEqual(claims["sub"], str(user["id"]))
            self.assertEqual(claims["exp"] - claims["iat"], 1800)
            self.assertGreater(claims["exp"], time.time())
            with self.assertRaises(jwt.InvalidSignatureError):
                jwt.decode(data["access_token"], "different-secret-key-with-at-least-32-bytes", algorithms=["HS256"])
            for invalid in ({**credentials, "password": "wrong-password"},
                            {**credentials, "email": "missing@example.com"}):
                with patch("app.services.user_service.create_access_token") as create_token:
                    status, error = await self.request("POST", "/api/users/login", invalid)
                    self.assertEqual(status, 401)
                    self.assertEqual(error, {"detail": "Неверный email или пароль"})
                    create_token.assert_not_called()

    # Проверяет доступ к профилю по токену и отказ без аутентификации.
    async def test_current_user(self):
        credentials = {"email": "alice@example.com", "password": "Example-password-123"}
        _, user = await self.request("POST", "/api/users/create", credentials)
        secret = "test-only-secret-key-with-at-least-32-bytes"
        with patch.dict(os.environ, {"JWT_SECRET_KEY": secret}):
            _, login = await self.request("POST", "/api/users/login", credentials)
            headers = [(b"authorization", ("Bearer " + login["access_token"]).encode())]
            status, profile = await self.request("GET", "/api/users/me", headers=headers)
            self.assertEqual((status, profile), (200, user))
            claims = {"sub": str(user["id"]), "exp": int(time.time()) + 1800}
            tokens = ["broken", jwt.encode(claims, "other-secret-key-with-at-least-32-bytes", algorithm="HS256")]
            for changes in ({"exp": 1}, {"sub": "999"}, {"sub": "abc"},
                            {"sub": "0"}, {"sub": "-1"}, {"sub": "9" * 100},
                            {"sub": 1}, {"exp": None}):
                tokens.append(jwt.encode({**claims, **changes}, secret, algorithm="HS256"))
            for missing in ("sub", "exp"):
                tokens.append(jwt.encode({k: v for k, v in claims.items() if k != missing}, secret, algorithm="HS256"))
            invalid_headers = [[], [(b"authorization", b"Basic abc")]]
            invalid_headers.extend([[(b"authorization", ("Bearer " + token).encode())] for token in tokens])
            for invalid in invalid_headers:
                status, error = await self.request("GET", "/api/users/me", headers=invalid)
                self.assertEqual(status, 401)
                self.assertEqual(error, {"detail": "Не удалось подтвердить пользователя"})
            with self.sessions() as db:
                db.delete(db.get(User, user["id"]))
                db.commit()
            status, _ = await self.request("GET", "/api/users/me", headers=headers)
            self.assertEqual(status, 401)

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
