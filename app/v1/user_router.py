from fastapi import Depends, APIRouter
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repository.user_repository import UserRepository
from app.schemas.user_schema import UserRead, UserCreate, UserLogin, TokenRead
from app.services.user_service import UserService


# Собирает сервис пользователей для текущего запроса.
def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))

router = APIRouter(prefix="/users", tags=["users"])


# Возвращает публичные данные текущего пользователя.
@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# Создаёт пользователя и возвращает его публичные данные.
@router.post("/create", response_model=UserRead, status_code=201)
def create_user(
        data: UserCreate,
        service: UserService = Depends(get_user_service)
):
    return service.create_user(data)


# Выдаёт токен после проверки email и пароля.
@router.post("/login", response_model=TokenRead)
def login_user(
        data: UserLogin,
        service: UserService = Depends(get_user_service),
):
    return service.login_user(data)
