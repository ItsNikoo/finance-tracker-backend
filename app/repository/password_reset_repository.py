from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.models.password_reset import PasswordResetRateLimit, PasswordResetToken
from app.models.user import User
from app.models.user_session import UserSession
from app.security import hash_token, utc_now


class PasswordResetRepository:
    def __init__(self, db: Session):
        self.db = db

    def allow_request(self, scope: str, value: str, limit: int, seconds: int) -> bool:
        now = utc_now()
        self.db.execute(delete(PasswordResetRateLimit).where(PasswordResetRateLimit.expires_at <= now))
        statement = insert(PasswordResetRateLimit).values(
            bucket_hash=hash_token(f"{scope}:{value}"), expires_at=now + timedelta(seconds=seconds), attempts=1,
        ).on_conflict_do_update(
            index_elements=[PasswordResetRateLimit.bucket_hash],
            set_={"attempts": PasswordResetRateLimit.attempts + 1},
            where=PasswordResetRateLimit.attempts < limit,
        )
        allowed = self.db.execute(statement).rowcount == 1
        self.db.commit()
        return allowed

    def issue(self, user_id: int, token_hash: str) -> None:
        now = utc_now()
        self.db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at <= now))
        self.db.execute(update(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None),
        ).values(used_at=now))
        self.db.add(PasswordResetToken(
            user_id=user_id, token_hash=token_hash, created_at=now,
            expires_at=now + timedelta(minutes=30),
        ))
        self.db.commit()

    def reset(self, token_hash: str, hashed_password: str) -> str | None:
        now = utc_now()
        valid_user = select(PasswordResetToken.user_id).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None), PasswordResetToken.expires_at > now,
        ).scalar_subquery()
        # Первым выполняется условная запись: два параллельных запроса не могут
        # независимо проверить один токен и оба сменить пароль.
        user_id = self.db.execute(update(User).where(User.id == valid_user).values(
            hashed_password=hashed_password,
        ).returning(User.id)).scalar_one_or_none()
        if user_id is None:
            self.db.rollback()
            return None
        self.db.execute(update(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None),
        ).values(used_at=now))
        self.db.execute(update(UserSession).where(
            UserSession.user_id == user_id, UserSession.revoked_at.is_(None),
        ).values(revoked_at=now))
        email = self.db.scalar(select(User.email).where(User.id == user_id))
        self.db.commit()
        return email
