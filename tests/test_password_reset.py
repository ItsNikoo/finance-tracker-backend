from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.password_reset import PasswordResetToken
from app.security import hash_token, utc_now


def test_password_reset_changes_password(authorized_client, request_password_reset, csrf_headers, login):
    token = request_password_reset()
    response = authorized_client.post(
        "/api/users/reset-password",
        json={"token": token, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert response.status_code == 204, response.text
    assert response.content == b""
    assert authorized_client.get("/api/users/me").status_code == 401

    # Старый пароль больше не подходит, новый позволяет войти.
    old_login = login()
    assert old_login.status_code == 401, old_login.text
    new_login = login(password="new-password-123")
    assert new_login.status_code == 200, new_login.text
    assert authorized_client.get("/api/users/me").status_code == 200


def test_password_reset_token_cannot_be_used_twice(authorized_client, request_password_reset, csrf_headers):
    token = request_password_reset()
    data = {"token": token, "new_password": "new-password-123"}
    first = authorized_client.post("/api/users/reset-password", json=data, headers=csrf_headers())
    assert first.status_code == 204, first.text
    second = authorized_client.post("/api/users/reset-password", json=data, headers=csrf_headers())
    assert second.status_code == 400, second.text


def test_password_reset_expired_token(authorized_client, request_password_reset, csrf_headers, db_engine):
    token = request_password_reset()
    # В тестовой БД делаем ссылку просроченной, без ожидания 30 минут.
    with Session(db_engine) as db:
        saved = db.get(PasswordResetToken, hash_token(token))
        assert saved is not None
        assert saved.token_hash != token
        saved.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

    response = authorized_client.post(
        "/api/users/reset-password", json={"token": token, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert response.status_code == 400, response.text
    # Неудачная попытка не завершает действующую сессию.
    assert authorized_client.get("/api/users/me").status_code == 200


def test_password_reset_unknown_token(client, csrf_headers):
    response = client.post(
        "/api/users/reset-password", json={"token": "x" * 43, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert response.status_code == 400, response.text


def test_new_reset_request_invalidates_old_link(authorized_client, request_password_reset, csrf_headers):
    first_token = request_password_reset()
    second_token = request_password_reset()
    assert first_token != second_token
    first = authorized_client.post(
        "/api/users/reset-password", json={"token": first_token, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert first.status_code == 400, first.text
    second = authorized_client.post(
        "/api/users/reset-password", json={"token": second_token, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert second.status_code == 204, second.text


def test_forgot_password_same_response_for_unknown_email(authorized_client, csrf_headers, mail_delivery):
    known = authorized_client.post(
        "/api/users/forgot-password", json={"email": "example@mail.ru"}, headers=csrf_headers(),
    )
    assert known.status_code == 202, known.text
    assert mail_delivery.call_count == 1
    unknown = authorized_client.post(
        "/api/users/forgot-password", json={"email": "missing@example.com"}, headers=csrf_headers(),
    )
    assert unknown.status_code == 202, unknown.text
    assert unknown.json() == known.json()
    # Для неизвестного адреса письмо не отправляется.
    assert mail_delivery.call_count == 1


def test_password_reset_revokes_all_user_sessions(
    authorized_client, second_client, csrf_headers, request_password_reset,
):
    # Входим в тот же аккаунт из второго браузера.
    second_login = second_client.post(
        "/api/users/login", json={"email": "example@mail.ru", "password": "password"},
        headers=csrf_headers(second_client),
    )
    assert second_login.status_code == 200, second_login.text
    assert second_client.get("/api/users/me").status_code == 200
    token = request_password_reset()
    response = authorized_client.post(
        "/api/users/reset-password", json={"token": token, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert response.status_code == 204, response.text
    assert authorized_client.get("/api/users/me").status_code == 401
    assert second_client.get("/api/users/me").status_code == 401
    refreshed = second_client.post("/api/users/refresh", headers=csrf_headers(second_client))
    assert refreshed.status_code == 401, refreshed.text


def test_password_reset_keeps_other_user_session(
    authorized_client, second_authorized_client, request_password_reset, csrf_headers,
):
    before = second_authorized_client.get("/api/users/me")
    assert before.status_code == 200, before.text
    token = request_password_reset()
    response = authorized_client.post(
        "/api/users/reset-password", json={"token": token, "new_password": "new-password-123"},
        headers=csrf_headers(),
    )
    assert response.status_code == 204, response.text
    after = second_authorized_client.get("/api/users/me")
    assert after.status_code == 200, after.text
    assert after.json() == before.json()


def test_forgot_password_email_limit(authorized_client, csrf_headers, mail_delivery):
    for _ in range(4):
        response = authorized_client.post(
            "/api/users/forgot-password", json={"email": "example@mail.ru"}, headers=csrf_headers(),
        )
        # Даже при ограничении ответ не раскрывает существование аккаунта.
        assert response.status_code == 202, response.text
    assert mail_delivery.call_count == 3


def test_forgot_password_ip_limit(client, csrf_headers, mail_delivery):
    for number in range(20):
        response = client.post(
            "/api/users/forgot-password", json={"email": f"missing{number}@example.com"},
            headers=csrf_headers(),
        )
        assert response.status_code == 202, response.text
    response = client.post(
        "/api/users/forgot-password", json={"email": "another@example.com"}, headers=csrf_headers(),
    )
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0
    mail_delivery.assert_not_called()


def test_reset_password_ip_limit(client, csrf_headers, mail_delivery):
    data = {"token": "x" * 43, "new_password": "new-password-123"}
    for _ in range(30):
        response = client.post("/api/users/reset-password", json=data, headers=csrf_headers())
        assert response.status_code == 400, response.text
    response = client.post("/api/users/reset-password", json=data, headers=csrf_headers())
    assert response.status_code == 429, response.text
    assert int(response.headers["retry-after"]) > 0
    mail_delivery.assert_not_called()
