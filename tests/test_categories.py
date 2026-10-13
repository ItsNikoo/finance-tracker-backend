import os
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import jwt
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
from app.database import enable_foreign_keys, get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.models.transaction import Transaction, TransactionType, PaymentMethod
from app.repository.user_repository import UserRepository
from app.repository.session_repository import SessionRepository
from app.security import hash_token, password_hasher, utc_now
from app.transaction_time import MOSCOW_TZ, moscow_now


# Проверяет API с cookies и отдельной базой данных.
class ApiTests(unittest.TestCase):
    # Применяет миграции и настраивает клиент для локального frontend.
    def setUp(self):
        self.secret = "test-only-secret-key-with-at-least-32-bytes"
        self.environment = patch.dict(os.environ, {
            "JWT_SECRET_KEY": self.secret, "COOKIE_SECURE": "true",
            "ALLOWED_ORIGINS": "http://localhost:5173,http://localhost:8000",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        event.listen(self.engine, "connect", enable_foreign_keys)
        self.sessions = sessionmaker(bind=self.engine)
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        main.app.dependency_overrides[get_db] = self.get_test_db
        self.client = self.new_client()

    # Освобождает тестовое подключение и зависимости.
    def tearDown(self):
        self.client.close()
        main.app.dependency_overrides.clear()
        self.engine.dispose()

    # Выдаёт сессию запроса с откатом ошибки.
    def get_test_db(self):
        with self.sessions() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    # Создаёт браузер с отдельным хранилищем cookies.
    def new_client(self):
        return TestClient(main.app, base_url="https://testserver", headers={"Origin": "http://localhost:5173"})

    # Получает CSRF-токен перед изменяющим запросом.
    def post(self, path, data=None, client=None):
        client = client or self.client
        csrf = client.get("/api/users/csrf")
        self.assertEqual(csrf.status_code, 200)
        return client.post(path, json=data, headers={"X-CSRF-Token": csrf.json()["csrf_token"]})

    # Создаёт пользователя и выполняет вход через API.
    def login(self, email="alice@example.com", client=None):
        client = client or self.client
        credentials = {"email": email, "password": "Example-password-123"}
        created = self.post("/api/users/create", credentials, client)
        self.assertIn(created.status_code, (201, 409))
        response = self.post("/api/users/login", credentials, client)
        self.assertEqual(response.status_code, 200)
        return response

    # Создаёт категорию для проверок транзакций.
    def category(self, kind="income"):
        response = self.post("/api/categories", {"name_en": "Other", "name_ru": "Прочее", "type": kind})
        self.assertEqual(response.status_code, 201)
        return response.json()

    # Проверяет публичный профиль и хеш пароля.
    def test_swagger_login_from_loopback_origin(self):
        with patch.dict(os.environ, {
            "COOKIE_SECURE": "false",
            "ALLOWED_ORIGINS": "http://localhost:8000,http://127.0.0.1:8000",
        }):
            with TestClient(main.app, base_url="http://127.0.0.1:8000", headers={
                "Origin": "http://127.0.0.1:8000",
            }) as client:
                credentials = {"email": "docs@example.com", "password": "Example-password-123"}
                self.assertEqual(self.post("/api/users/register", credentials, client).status_code, 201)
                self.assertEqual(self.post("/api/users/login", credentials, client).status_code, 200)
                self.assertEqual(client.get("/api/users/me").json()["email"], credentials["email"])
                self.assertEqual(client.get("/api/transactions/balance").status_code, 200)
                csrf = client.get("/api/users/csrf").json()["csrf_token"]
                self.assertEqual(client.post("/api/users/logout", headers={
                    "X-CSRF-Token": csrf, "Origin": "http://evil.example",
                }).status_code, 403)
                self.assertEqual(client.post("/api/users/logout").status_code, 403)
                self.assertEqual(self.post("/api/users/logout", client=client).status_code, 204)
                self.assertEqual(client.get("/api/users/me").status_code, 401)

    # Проверяет публичный профиль и хеш пароля.
    def test_registration_and_password(self):
        response = self.post("/api/users/create", {"email": " Alice@Example.com ", "password": "Example-password-123"})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(set(data), {"id", "email", "created_at"})
        self.assertEqual(data["email"], "alice@example.com")
        with self.sessions() as db:
            user = db.get(User, data["id"])
            self.assertTrue(password_hasher.verify("Example-password-123", user.hashed_password))
            self.assertFalse(password_hasher.verify("wrong", user.hashed_password))
            self.assertIsNotNone(user.created_at)
        duplicate = self.post("/api/users/create", {"email": "ALICE@example.com", "password": "Example-password-123"})
        self.assertEqual(duplicate.status_code, 409)

    # Проверяет формат email и допустимую длину пароля.
    def test_invalid_registration(self):
        for email, password in (("invalid", "Example-password-123"), ("a@example.com", "short"), ("a@example.com", "x" * 129)):
            self.assertEqual(self.post("/api/users/create", {"email": email, "password": password}).status_code, 422)

    # Проверяет обработку конфликта email после предварительного поиска.
    def test_registration_race(self):
        self.login()
        with self.sessions() as db:
            user = db.scalar(select(User))
            repository = UserRepository(db)
            with self.assertRaises(IntegrityError):
                repository.create(User(email=user.email, hashed_password="test-only"))
            self.assertIsNotNone(repository.get_user_by_email(user.email))

    # Проверяет свойства cookies и отсутствие токенов входа в JSON.
    def test_login_cookies_and_me(self):
        response = self.login()
        self.assertEqual(set(response.json()), {"user", "csrf_token"})
        cookies = response.headers.get_list("set-cookie")
        self.assertEqual(len(cookies), 3)
        for cookie in cookies:
            self.assertIn("HttpOnly", cookie)
            self.assertIn("Secure", cookie)
            self.assertIn("SameSite=lax", cookie)
            self.assertIn("Path=/", cookie)
            self.assertNotIn("Domain=", cookie)
        access = self.client.cookies["access_token"]
        claims = jwt.decode(access, self.secret, algorithms=["HS256"])
        self.assertEqual(claims["exp"] - claims["iat"], 900)
        with self.sessions() as db:
            session = db.get(UserSession, claims["sid"])
            self.assertEqual(session.refresh_token_hash, hash_token(self.client.cookies["refresh_token"]))
            self.assertNotEqual(session.refresh_token_hash, self.client.cookies["refresh_token"])
        me = self.client.get("/api/users/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json(), response.json()["user"])
        self.assertEqual(me.headers["cache-control"], "no-store")

    # Проверяет отказ при неизвестном email и неверном пароле.
    def test_invalid_login(self):
        self.post("/api/users/create", {"email": "alice@example.com", "password": "Example-password-123"})
        for email, password in (("alice@example.com", "wrong"), ("missing@example.com", "wrong")):
            response = self.post("/api/users/login", {"email": email, "password": password})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {"detail": "Неверный email или пароль"})
        with self.sessions() as db:
            self.assertEqual(db.scalars(select(UserSession)).all(), [])

    # Проверяет CSRF и Origin до выполнения изменяющего запроса.
    def test_csrf_and_origin(self):
        data = {"email": "alice@example.com", "password": "Example-password-123"}
        self.assertEqual(self.client.post("/api/users/create", json=data).status_code, 403)
        csrf = self.client.get("/api/users/csrf").json()["csrf_token"]
        self.assertEqual(self.client.post("/api/users/create", json=data, headers={"X-CSRF-Token": "bad"}).status_code, 403)
        self.assertEqual(self.client.post("/api/users/create", json=data, headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/users/csrf", headers={"Origin": "https://evil.example"}).status_code, 403)
        anonymous_csrf = csrf
        self.login()
        self.assertEqual(self.client.post("/api/users/logout", headers={"X-CSRF-Token": anonymous_csrf}).status_code, 403)
        csrf = self.client.get("/api/users/csrf").json()["csrf_token"]
        self.assertEqual(self.client.get("/api/users/csrf").json()["csrf_token"], csrf)
        for path in ("/api/users/login", "/api/users/refresh", "/api/users/logout", "/api/categories", "/api/transactions"):
            self.assertEqual(self.client.post(path, json={}).status_code, 403)
        without_origin = self.new_client()
        try:
            without_origin.headers.pop("origin")
            without_origin.cookies.update(self.client.cookies)
            self.assertEqual(without_origin.post("/api/users/logout", headers={"X-CSRF-Token": csrf}).status_code, 403)
        finally:
            without_origin.close()

    # Проверяет отказ CSRF-токену другой сессии даже при совпадении cookie и заголовка.
    def test_csrf_session_binding(self):
        self.login()
        other = self.new_client()
        try:
            other_token = self.login("bob@example.com", other).json()["csrf_token"]
            self.client.cookies.set("csrf_token", other_token, domain="testserver.local", path="/")
            self.assertEqual(self.client.post("/api/users/logout", headers={"X-CSRF-Token": other_token}).status_code, 403)
            self.assertEqual(self.client.get("/api/users/me").status_code, 200)
        finally:
            other.close()

    # Проверяет обновление после истечения access и однократность refresh.
    def test_refresh_rotation(self):
        self.login()
        old_refresh = self.client.cookies["refresh_token"]
        claims = jwt.decode(self.client.cookies["access_token"], self.secret, algorithms=["HS256"])
        expired = jwt.encode({**claims, "iat": 1, "exp": 2}, self.secret, algorithm="HS256")
        self.client.cookies.set("access_token", expired, domain="testserver.local", path="/")
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        response = self.post("/api/users/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.client.cookies["refresh_token"], old_refresh)
        self.assertEqual(self.client.get("/api/users/me").status_code, 200)
        self.client.cookies.set("refresh_token", old_refresh, domain="testserver.local", path="/")
        self.assertEqual(self.post("/api/users/refresh").status_code, 401)

    # Проверяет немедленный отзыв скопированного access после выхода.
    def test_logout_and_other_device(self):
        self.login()
        attacker = self.new_client()
        other = self.new_client()
        try:
            attacker.cookies.update(self.client.cookies)
            self.login(client=other)
            self.assertEqual(self.post("/api/users/logout").status_code, 204)
            self.assertNotIn("access_token", self.client.cookies)
            self.assertNotIn("refresh_token", self.client.cookies)
            self.assertNotIn("csrf_token", self.client.cookies)
            self.assertEqual(attacker.get("/api/users/me").status_code, 401)
            self.assertEqual(self.post("/api/users/refresh", client=attacker).status_code, 401)
            self.assertEqual(other.get("/api/users/me").status_code, 200)
            self.assertEqual(self.post("/api/users/logout").status_code, 204)
        finally:
            attacker.close()
            other.close()

    # Проверяет выход по refresh при истёкшем access.
    def test_logout_without_access(self):
        self.login()
        self.client.cookies.delete("access_token")
        self.assertEqual(self.post("/api/users/logout").status_code, 204)
        with self.sessions() as db:
            self.assertIsNotNone(db.scalar(select(UserSession)).revoked_at)

    # Проверяет абсолютный срок сессии и отказ просроченному refresh.
    def test_session_expiration(self):
        self.login()
        with self.sessions() as db:
            session = db.scalar(select(UserSession))
            session.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)
        self.assertEqual(self.post("/api/users/refresh").status_code, 401)

    # Проверяет подпись, назначение и обязательные поля access.
    def test_invalid_access(self):
        self.login()
        claims = jwt.decode(self.client.cookies["access_token"], self.secret, algorithms=["HS256"])
        variants = ["bad", jwt.encode(claims, "other-test-secret-key-with-at-least-32-bytes", algorithm="HS256")]
        for change in ({"sub": "0"}, {"sub": "9" * 100}, {"sub": "999"}, {"sid": "a" * 32}, {"kind": "csrf"}, {"exp": 1}):
            variants.append(jwt.encode({**claims, **change}, self.secret, algorithm="HS256"))
        variants.append(jwt.encode({k: v for k, v in claims.items() if k != "sid"}, self.secret, algorithm="HS256"))
        for token in variants:
            self.client.cookies.set("access_token", token, domain="testserver.local", path="/")
            self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    # Проверяет атомарную замену refresh при двух обновлениях старого значения.
    def test_refresh_compare_and_swap(self):
        self.login()
        with self.sessions() as db:
            session = db.scalar(select(UserSession))
            session_id, old_hash = session.id, session.refresh_token_hash
            repository = SessionRepository(db)
            self.assertTrue(repository.rotate(session_id, old_hash, hash_token("first"), utc_now()))
            self.assertFalse(repository.rotate(session_id, old_hash, hash_token("second"), utc_now()))
            self.assertEqual(db.get(UserSession, session_id).refresh_token_hash, hash_token("first"))

    # Проверяет точный разрешённый Origin и передачу credentials через CORS.
    def test_cors(self):
        response = self.client.options("/api/users/login", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        denied = self.client.options("/api/users/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        self.assertNotIn("access-control-allow-origin", denied.headers)

    # Проверяет категории, уникальность и валидацию названий.
    def test_categories(self):
        self.assertEqual(self.client.get("/api/categories").json(), [])
        category = self.category()
        self.assertEqual(self.client.get(f'/api/categories/{category["id"]}').json(), category)
        for duplicate in ({"name_en": "Other", "name_ru": "Другое", "type": "income"},
                          {"name_en": "Different", "name_ru": "Прочее", "type": "income"}):
            self.assertEqual(self.post("/api/categories", duplicate).status_code, 409)
        self.category("expense")
        self.assertEqual(len(self.client.get("/api/categories").json()), 2)
        self.assertEqual(self.client.get("/api/categories/999").status_code, 404)
        for invalid in ({}, {"name_en": " ", "name_ru": "Test", "type": "income"},
                        {"name_en": "x" * 101, "name_ru": "Test", "type": "income"}):
            self.assertEqual(self.post("/api/categories", invalid).status_code, 422)

    # Проверяет создание транзакций и изоляцию двух пользователей.
    def test_transactions(self):
        category = self.category()
        data = {"type": "income", "amount": "12.34", "category_id": category["id"], "payment_method": "cash"}
        self.assertEqual(self.client.get("/api/transactions").status_code, 401)
        self.assertEqual(self.post("/api/transactions", data).status_code, 401)
        first = self.login().json()["user"]
        created = self.post("/api/transactions", {**data, "user_id": 999})
        self.assertEqual(created.status_code, 200)
        identifier = created.json()["id"]
        with self.sessions() as db:
            self.assertEqual(db.get(Transaction, identifier).user_id, first["id"])
        self.assertEqual(self.client.get(f"/api/transactions/{identifier}").json(), created.json())
        self.assertEqual(len(self.client.get("/api/transactions").json()), 1)
        for invalid, status in (({**data, "type": "expense"}, 400), ({**data, "category_id": 999}, 404),
                                ({**data, "amount": "0"}, 422), ({"amount": "1", "type": "income"}, 422)):
            self.assertEqual(self.post("/api/transactions", invalid).status_code, status)
        other = self.new_client()
        try:
            self.login("bob@example.com", other)
            self.assertEqual(other.get("/api/transactions").json(), [])
            self.assertEqual(other.get(f"/api/transactions/{identifier}").status_code, 404)
        finally:
            other.close()

    # Проверяет текущий месяц, границы года, знак баланса и изоляцию пользователей.
    def test_monthly_balance(self):
        path = "/api/transactions/balance"
        self.assertEqual(self.client.get(path).status_code, 401)
        credentials = {"email": "alice@example.com", "password": "Example-password-123"}
        registered = self.post("/api/users/register", credentials)
        self.assertEqual(registered.status_code, 201)
        logged_in = self.post("/api/users/login", credentials)
        self.assertEqual(logged_in.status_code, 200)
        user_id = logged_in.json()["user"]["id"]
        income_category = self.category("income")["id"]
        expense_category = self.category("expense")["id"]
        with patch("app.services.transaction_service.moscow_now") as clock:
            clock.return_value = datetime(2026, 12, 15, 12, tzinfo=MOSCOW_TZ)
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), 0)

            with self.sessions() as db:
                other = User(email="other@example.com", hashed_password="test-only")
                db.add(other)
                db.flush()
                expense = Transaction(
                    payment_method=PaymentMethod.CASH,
                    user_id=user_id, category_id=expense_category,
                    type=TransactionType.EXPENSE, amount=Decimal("2.10"),
                    occurred_at=datetime(2026, 12, 31, 23, 59, 59, 999999),
                    created_at=datetime(2020, 1, 1),
                )
                db.add(expense)
                for owner, date, amount in (
                    (user_id, datetime(2026, 11, 30, 23, 59, 59, 999999), "1000"),
                    (user_id, datetime(2026, 12, 1), "12.34"),
                    (user_id, datetime(2027, 1, 1), "1000"),
                    (other.id, datetime(2026, 12, 15), "5000"),
                ):
                    db.add(Transaction(
                        payment_method=PaymentMethod.CASH,
                        user_id=owner, category_id=income_category,
                        type=TransactionType.INCOME, amount=Decimal(amount), occurred_at=date,
                        created_at=datetime(2020, 1, 1),
                    ))
                db.commit()
                expense_id = expense.id

            self.assertEqual(self.client.get(path).json(), 10.24)
            self.assertEqual(self.client.get(path, params={"month": 12}).json(), 10.24)
            self.assertEqual(self.client.get(path, params={"month": 11}).json(), 1000)
            self.assertEqual(self.client.get(path, params={"month": 1}).json(), 0)
            for invalid_month in (0, 13, -1, "bad", "1.5", ""):
                self.assertEqual(self.client.get(path, params={"month": invalid_month}).status_code, 422)
            for amount, expected in (("20.00", -7.66), ("12.34", 0)):
                with self.sessions() as db:
                    db.get(Transaction, expense_id).amount = Decimal(amount)
                    db.commit()
                self.assertEqual(self.client.get(path).json(), expected)

            clock.return_value = datetime(2027, 1, 15, 12, tzinfo=MOSCOW_TZ)
            self.assertEqual(self.client.get(path).json(), 1000)
            self.assertEqual(self.client.get(path, params={"month": 12}).json(), 0)

    def test_transaction_occurrence_date(self):
        credentials = {"email": "alice@example.com", "password": "Example-password-123"}
        self.assertEqual(self.post("/api/users/register", credentials).status_code, 201)
        self.assertEqual(self.post("/api/users/login", credentials).status_code, 200)
        category_id = self.category()["id"]
        data = {"category_id": category_id, "type": "income", "amount": "10.25", "payment_method": "card", "description": "Покупка"}
        before = moscow_now()
        default = self.post("/api/transactions", data)
        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.json()["payment_method"], "card")
        self.assertEqual(default.json()["description"], "Покупка")
        occurred = datetime.fromisoformat(default.json()["occurred_at"])
        self.assertEqual(occurred.utcoffset(), timedelta(hours=3))
        self.assertLessEqual(before, occurred)
        self.assertLessEqual(occurred, moscow_now())
        with self.sessions() as db:
            db.get(Transaction, default.json()["id"]).occurred_at = datetime(2000, 1, 1)
            db.commit()

        created = self.post("/api/transactions", {
            **data, "occurred_at": "2026-11-30T21:00:00Z",
        })
        self.assertEqual(created.status_code, 200)
        record = created.json()
        self.assertEqual(record["occurred_at"], "2026-12-01T00:00:00+03:00")
        path = f'/api/transactions/{record["id"]}'
        self.assertEqual(self.client.get(path).json(), record)

        csrf = self.client.get("/api/users/csrf").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        with patch("app.services.transaction_service.moscow_now") as clock:
            clock.return_value = datetime(2026, 12, 15, tzinfo=MOSCOW_TZ)
            self.assertEqual(self.client.get("/api/transactions/balance").json(), 10.25)
            updated = self.client.patch(path, json={"occurred_at": "2026-11-30T23:59:59"}, headers=headers)
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["occurred_at"], "2026-11-30T23:59:59+03:00")
            self.assertEqual(updated.json()["created_at"], record["created_at"])
            self.assertEqual(updated.json()["amount"], record["amount"])
            self.assertEqual(self.client.get("/api/transactions/balance").json(), 0)
        for invalid in ({}, {"occurred_at": None}, {"occurred_at": "bad"},
                        {"occurred_at": "2026-12-01T00:00:00", "user_id": 999}):
            self.assertEqual(self.client.patch(path, json=invalid, headers=headers).status_code, 422)
        for invalid in (None, "bad"):
            self.assertEqual(self.post("/api/transactions", {**data, "occurred_at": invalid}).status_code, 422)
        for method in ("cash", "transfer"):
            response = self.post("/api/transactions", {**data, "payment_method": method, "description": None})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["payment_method"], method)
            self.assertIsNone(response.json()["description"])
        self.assertEqual(self.client.patch("/api/transactions/999", json={
            "occurred_at": "2026-12-01T00:00:00",
        }, headers=headers).status_code, 404)

        other = self.new_client()
        try:
            date = {"occurred_at": "2026-12-02T12:00:00+03:00"}
            anonymous_csrf = other.get("/api/users/csrf").json()["csrf_token"]
            self.assertEqual(other.patch(path, json=date, headers={
                "X-CSRF-Token": anonymous_csrf,
            }).status_code, 401)
            other_credentials = {**credentials, "email": "bob@example.com"}
            self.assertEqual(self.post("/api/users/register", other_credentials, other).status_code, 201)
            login = self.post("/api/users/login", other_credentials, other)
            self.assertEqual(login.status_code, 200)
            self.assertEqual(other.patch(path, json=date, headers={
                "X-CSRF-Token": login.json()["csrf_token"],
            }).status_code, 404)
            self.assertEqual(self.client.get(path).json(), updated.json())
        finally:
            other.close()

    # Проверяет внешние ключи и обязательность владельца на уровне БД.
    def test_database_constraints(self):
        self.login()
        self.category()
        with self.engine.begin() as connection:
            for statement in (
                "INSERT INTO categories (name_en, name_ru, type) VALUES ('Other', 'Другое', 'INCOME')",
                "INSERT INTO transactions (category_id, type, amount, created_at) VALUES (1, 'INCOME', 1, CURRENT_TIMESTAMP)",
                "INSERT INTO transactions (category_id, user_id, type, amount, created_at) VALUES (999, 1, 'INCOME', 1, CURRENT_TIMESTAMP)",
            ):
                with self.assertRaises(IntegrityError):
                    connection.exec_driver_sql(statement)
