from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# Хранит срок действия и состояние отдельного входа пользователя.
class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (UniqueConstraint("refresh_token_hash", name="uq_user_sessions_refresh_hash"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", name="fk_user_sessions_user_id_users"), index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
