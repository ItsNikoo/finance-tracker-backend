from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import jwt
from dotenv import load_dotenv
from pwdlib import PasswordHash


# Загружает настройки из .env в корне проекта.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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


# Создаёт подписанный токен доступа на 30 минут.
def create_access_token(user_id: int) -> str:
    secret = get_jwt_secret()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# Проверяет токен и возвращает идентификатор пользователя.
def decode_access_token(token: str) -> int:
    payload = jwt.decode(
        token, get_jwt_secret(), algorithms=["HS256"],
        options={"require": ["sub", "exp"]},
    )
    subject = payload["sub"]
    if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal():
        raise jwt.InvalidTokenError("Некорректный идентификатор пользователя")
    if len(subject) > 19:
        raise jwt.InvalidTokenError("Некорректный идентификатор пользователя")
    user_id = int(subject)
    if not 0 < user_id <= 9223372036854775807:
        raise jwt.InvalidTokenError("Некорректный идентификатор пользователя")
    return user_id
