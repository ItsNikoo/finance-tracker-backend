from datetime import datetime, timedelta, timezone

import jwt

from app.security import get_jwt_secret


def test_refresh_updates_access(authorized_client, csrf_headers):
    # Удаляем access-cookie: новый доступ должен появиться через refresh.
    authorized_client.cookies.delete("access_token")
    assert authorized_client.get("/api/users/me").status_code == 401
    old_refresh = authorized_client.cookies.get("refresh_token")

    response = authorized_client.post("/api/users/refresh", headers=csrf_headers())
    assert response.status_code == 200, response.text
    assert authorized_client.cookies.get("access_token")
    assert authorized_client.cookies.get("refresh_token") != old_refresh
    profile = authorized_client.get("/api/users/me")
    assert profile.status_code == 200, profile.text
    assert profile.json() == response.json()["user"]


def test_refresh_after_logout_is_rejected(authorized_client, csrf_headers):
    old_refresh = authorized_client.cookies.get("refresh_token")
    response = authorized_client.post("/api/users/logout", headers=csrf_headers())
    assert response.status_code == 204, response.text

    # Возвращаем старую cookie, как будто её сохранил посторонний.
    authorized_client.cookies.set("refresh_token", old_refresh)
    response = authorized_client.post("/api/users/refresh", headers=csrf_headers())
    assert response.status_code == 401, response.text
    assert authorized_client.get("/api/users/me").status_code == 401


def test_expired_access_can_be_refreshed(authorized_client, csrf_headers):
    # Меняем срок токена в тесте, не ждём настоящие 15 минут.
    token = authorized_client.cookies.get("access_token")
    claims = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    claims["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = jwt.encode(claims, get_jwt_secret(), algorithm="HS256")
    cookie = next(item for item in authorized_client.cookies.jar if item.name == "access_token")
    authorized_client.cookies.delete("access_token")
    authorized_client.cookies.set("access_token", expired, domain=cookie.domain, path=cookie.path)

    assert authorized_client.get("/api/users/me").status_code == 401
    response = authorized_client.post("/api/users/refresh", headers=csrf_headers())
    assert response.status_code == 200, response.text
    assert authorized_client.get("/api/users/me").status_code == 200
