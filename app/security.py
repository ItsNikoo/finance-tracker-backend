from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets

import jwt
from pwdlib import PasswordHash

from app.settings import ACCESS_TOKEN_SECONDS


password_hasher = PasswordHash.recommended()


# Создаёт хеш пароля с индивидуальной солью.
def hash_password(password: str) -> str:
    return password_hasher.hash(password)


# Возвращает настроенный ключ подписи токенов.
def get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("Задайте JWT_SECRET_KEY длиной не менее 32 байт")
    return secret


# Возвращает UTC без часового пояса для хранения в SQLite.
def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Создаёт access-токен, связанный с серверной сессией.
def create_access_token(user_id: int, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sub": str(user_id), "sid": session_id, "kind": "access",
        "iat": now, "exp": now + timedelta(seconds=ACCESS_TOKEN_SECONDS),
    }, get_jwt_secret(), algorithm="HS256")


# Проверяет подпись, срок действия и назначение access-токена.
def decode_access_token(token: str) -> tuple[int, str]:
    payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"],
                         options={"require": ["sub", "sid", "exp", "kind"]})
    subject = payload["sub"]
    session_id = payload["sid"]
    if (payload["kind"] != "access" or not isinstance(subject, str)
            or not subject.isascii() or not subject.isdecimal() or len(subject) > 19
            or not isinstance(session_id, str) or len(session_id) != 32):
        raise jwt.InvalidTokenError("Некорректный токен доступа")
    user_id = int(subject)
    if not 0 < user_id <= 9223372036854775807:
        raise jwt.InvalidTokenError("Некорректный идентификатор пользователя")
    return user_id, session_id


# Создаёт случайный refresh-токен с идентификатором сессии.
def create_refresh_token(session_id: str) -> str:
    return session_id + "." + secrets.token_urlsafe(32)


# Хеширует случайный токен перед сохранением в БД.
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Создаёт подписанный CSRF-токен для сессии или формы входа.
def create_csrf_token(session_id: str, lifetime: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({
        "sid": session_id, "kind": "csrf", "nonce": secrets.token_urlsafe(32),
        "iat": now, "exp": now + timedelta(seconds=lifetime),
    }, get_jwt_secret(), algorithm="HS256")


# Проверяет CSRF-токен и возвращает его привязку к сессии.
def decode_csrf_token(token: str) -> str:
    payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"],
                         options={"require": ["sid", "kind", "nonce", "exp"]})
    if payload["kind"] != "csrf" or not isinstance(payload["sid"], str):
        raise jwt.InvalidTokenError("Некорректный CSRF-токен")
    return payload["sid"]
