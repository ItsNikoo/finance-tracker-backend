from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User


# Выполняет запросы к таблице пользователей.
class UserRepository:
    # Принимает сессию текущего запроса.
    def __init__(self, db: Session):
        self.db = db

    # Сохраняет пользователя и откатывает конфликт записи.
    def create(self, user: User) -> User:
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(user)
        return user

    # Ищет пользователя по нормализованному email.
    def get_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.strip().lower()))

    # Ищет пользователя по идентификатору.
    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)
