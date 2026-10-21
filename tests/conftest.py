from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import enable_foreign_keys, get_db


@pytest.fixture
def test_settings(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-secret-key-with-at-least-32-bytes",
    )
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173",
    )

    # На случай будущих тестов восстановления пароля.
    monkeypatch.setenv("MAIL_MODE", "file")
    monkeypatch.setenv(
        "PASSWORD_RESET_URL",
        "http://localhost:5173/reset-password",
    )


@pytest.fixture
def db_engine(test_settings, tmp_path):
    database_path = tmp_path / "test.db"

    engine = create_engine(
        URL.create("sqlite", database=str(database_path)),
        connect_args={"check_same_thread": False},
    )

    event.listen(engine, "connect", enable_foreign_keys)

    try:
        project_root = Path(__file__).resolve().parents[1]
        config = Config(str(project_root / "alembic.ini"))
        config.set_main_option(
            "script_location",
            str(project_root / "migrations"),
        )

        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def client(db_engine):
    from main import app

    test_sessions = sessionmaker(
        bind=db_engine,
        autoflush=False,
    )

    def override_get_db():
        with test_sessions() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(
                app,
                base_url="http://testserver",
                headers={"Origin": "http://localhost:5173"},
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def csrf_headers(client):
    # Можно получить CSRF как для основного, так и для второго клиента.
    def get_headers(request_client=None):
        if request_client is None:
            request_client = client
        response = request_client.get("/api/users/csrf")

        assert response.status_code == 200, response.text

        token = response.json()["csrf_token"]

        return {"X-CSRF-Token": token}

    return get_headers


@pytest.fixture
def register(client, csrf_headers):
    def _register(
            email="example@mail.ru",
            password="password",
    ):
        return client.post(
            "/api/users/register",
            json={
                "email": email,
                "password": password,
            },
            headers=csrf_headers(),
        )

    return _register


@pytest.fixture
def login(client, csrf_headers):
    def _login(
            email="example@mail.ru",
            password="password",
    ):
        return client.post(
            "/api/users/login",
            json={
                "email": email,
                "password": password,
            },
            headers=csrf_headers(),
        )

    return _login

@pytest.fixture
def authorized_client(register, login, client):
    registered = register()
    assert registered.status_code == 201, registered.text
    logged_in = login()
    assert logged_in.status_code == 200, logged_in.text
    return client


@pytest.fixture
def create_category(authorized_client, csrf_headers):
    def _create_category(
        name_en="Test Category",
        name_ru="Тестовая категория",
        type="income"
    ):
        return authorized_client.post(
            "/api/categories",
            json={
                "name_en": name_en,
                "name_ru": name_ru,
                "type": type
            },
            headers=csrf_headers()
        )

    return _create_category


@pytest.fixture
def second_client(client):
    from main import app

    # База общая с первым клиентом, но cookies у каждого свои.
    with TestClient(
        app, base_url="http://testserver",
        headers={"Origin": "http://localhost:5173"},
    ) as other_client:
        yield other_client


@pytest.fixture
def second_authorized_client(second_client, csrf_headers):
    data = {"email": "second@example.com", "password": "password"}
    registered = second_client.post(
        "/api/users/register", json=data, headers=csrf_headers(second_client),
    )
    assert registered.status_code == 201, registered.text
    logged_in = second_client.post(
        "/api/users/login", json=data, headers=csrf_headers(second_client),
    )
    assert logged_in.status_code == 200, logged_in.text
    return second_client


@pytest.fixture
def transaction_data(authorized_client):
    # Находим категорию расхода по типу, а не по заранее известному ID.
    response = authorized_client.get("/api/categories")
    assert response.status_code == 200, response.text
    category = next(item for item in response.json() if item["type"] == "expense")
    return {
        "category_id": category["id"],
        "type": "expense",
        "payment_method": "cash",
        "description": "Тестовая операция",
        "amount": "100.00",
        "occurred_at": "2026-06-01T12:00:00+03:00",
    }


@pytest.fixture
def create_transaction(authorized_client, csrf_headers, transaction_data):
    def _create_transaction(**changes):
        data = transaction_data.copy()
        data.update(changes)
        return authorized_client.post(
            "/api/transactions", json=data, headers=csrf_headers(),
        )

    return _create_transaction


@pytest.fixture
def mail_delivery(monkeypatch):
    # Перехватываем письма: тесты не отправляют их в Gmail и не создают файлы.
    delivery = Mock()
    monkeypatch.setattr("app.services.password_reset_service.deliver_mail", delivery)
    return delivery


@pytest.fixture
def request_password_reset(client, csrf_headers, mail_delivery):
    def _request_password_reset(email="example@mail.ru"):
        previous_count = mail_delivery.call_count
        response = client.post(
            "/api/users/forgot-password", json={"email": email},
            headers=csrf_headers(),
        )
        assert response.status_code == 202, response.text
        assert mail_delivery.call_count == previous_count + 1
        # Ссылка находится в тексте перехваченного письма.
        body = mail_delivery.call_args.args[3]
        return body.split("#token=", 1)[1].split()[0]

    return _request_password_reset
