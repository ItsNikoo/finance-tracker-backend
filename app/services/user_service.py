from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.repository.user_repository import UserRepository
from app.schemas.user_schema import UserCreate
from app.security import hash_password


# Проверяет правила работы с пользователями.
class UserService:
    # Принимает репозиторий пользователей.
    def __init__(self, repository: UserRepository):
        self.repository = repository

    # Проверяет email и сохраняет пользователя с хешем пароля.
    def create_user(self, data: UserCreate) -> User:
        if self.repository.get_user_by_email(data.email):
            raise HTTPException(409, "Пользователь с таким email уже существует")
        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
        )
        try:
            return self.repository.create(user)
        except IntegrityError as exc:
            # Учитывает одновременную регистрацию одного email.
            if self.repository.get_user_by_email(data.email):
                raise HTTPException(409, "Пользователь с таким email уже существует") from exc
            raise

    # Возвращает пользователя по идентификатору.
    def get_user_by_id(self, user_id: int) -> User | None:
        return self.repository.get_user_by_id(user_id)

    # Возвращает пользователя по email.
    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_user_by_email(email)
