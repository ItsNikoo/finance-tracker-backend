import os
import unittest
from datetime import timedelta
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
from app.models.transaction import Transaction
from app.repository.user_repository import UserRepository
from app.repository.session_repository import SessionRepository
from app.security import hash_token, password_hasher, utc_now


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
        data = {"type": "income", "amount": "12.34", "category_id": category["id"]}
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
