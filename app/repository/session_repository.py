from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.user_session import UserSession


# Выполняет запросы к сессиям пользователей.
class SessionRepository:
    # Принимает сессию текущего запроса.
    def __init__(self, db: Session):
        self.db = db

    # Ищет сессию по публичному идентификатору.
    def get_by_id(self, session_id: str) -> UserSession | None:
        return self.db.get(UserSession, session_id)

    # Сохраняет новый вход пользователя.
    def create(self, session: UserSession) -> UserSession:
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    # Заменяет refresh только если старый токен ещё не использован.
    def rotate(self, session_id: str, old_hash: str, new_hash: str, now: datetime) -> bool:
        result = self.db.execute(update(UserSession).where(
            UserSession.id == session_id,
            UserSession.refresh_token_hash == old_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        ).values(refresh_token_hash=new_hash))
        self.db.commit()
        return result.rowcount == 1

    # Немедленно отзывает текущую сессию.
    def revoke(self, session_id: str, now: datetime) -> None:
        self.db.execute(update(UserSession).where(
            UserSession.id == session_id, UserSession.revoked_at.is_(None),
        ).values(revoked_at=now))
        self.db.commit()
