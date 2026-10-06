from datetime import timedelta
import secrets
from uuid import uuid4

import jwt
from fastapi import HTTPException

from app.models.user_session import UserSession
from app.repository.session_repository import SessionRepository
from app.repository.user_repository import UserRepository
from app.security import (
    create_access_token, create_refresh_token, decode_access_token, hash_token, utc_now,
)
from app.settings import SESSION_SECONDS


# Управляет выдачей, продлением и отзывом сессий.
class SessionService:
    # Принимает репозитории одной сессии БД.
    def __init__(self, repository: SessionRepository, users: UserRepository):
        self.repository = repository
        self.users = users

    # Находит действующую сессию существующего пользователя.
    def get_active(self, session_id: str) -> UserSession | None:
        session = self.repository.get_by_id(session_id)
        if (session is None or session.revoked_at is not None
                or session.expires_at <= utc_now()
                or self.users.get_user_by_id(session.user_id) is None):
            return None
        return session

    # Проверяет access-токен вместе с серверным состоянием сессии.
    def from_access(self, token: str | None) -> UserSession | None:
        if not token:
            return None
        try:
            user_id, session_id = decode_access_token(token)
        except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
            return None
        session = self.get_active(session_id)
        return session if session is not None and session.user_id == user_id else None

    # Проверяет refresh-токен по сохранённому хешу.
    def from_refresh(self, token: str | None) -> UserSession | None:
        if not token or len(token) > 256:
            return None
        session_id, separator, random_part = token.partition(".")
        if not separator or len(session_id) != 32 or not random_part:
            return None
        session = self.get_active(session_id)
        if session is None or not secrets.compare_digest(session.refresh_token_hash, hash_token(token)):
            return None
        return session

    # Создаёт отдельную сессию и пару токенов для нового входа.
    def create(self, user_id: int) -> tuple[UserSession, str, str]:
        session_id = uuid4().hex
        refresh = create_refresh_token(session_id)
        access = create_access_token(user_id, session_id)
        now = utc_now()
        session = self.repository.create(UserSession(
            id=session_id, user_id=user_id, refresh_token_hash=hash_token(refresh),
            created_at=now, expires_at=now + timedelta(seconds=SESSION_SECONDS),
        ))
        return session, access, refresh

    # Атомарно заменяет refresh и выдаёт новый access без продления срока сессии.
    def refresh(self, token: str | None) -> tuple[UserSession, str, str]:
        session = self.from_refresh(token)
        if session is None:
            raise HTTPException(401, "Сессия истекла или недействительна")
        refresh = create_refresh_token(session.id)
        access = create_access_token(session.user_id, session.id)
        if not self.repository.rotate(session.id, hash_token(token), hash_token(refresh), utc_now()):
            raise HTTPException(401, "Refresh-токен уже использован")
        return session, access, refresh

    # Отзывает сессию, включая все выданные для неё access-токены.
    def revoke(self, session: UserSession) -> None:
        self.repository.revoke(session.id, utc_now())
