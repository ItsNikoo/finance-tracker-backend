import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.repository.user_repository import UserRepository
from app.security import decode_access_token


bearer_scheme = HTTPBearer(auto_error=False)


# Определяет текущего пользователя по токену доступа.
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=401,
        detail="Не удалось подтвердить пользователя",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError) as exc:
        raise unauthorized from exc
    user = UserRepository(db).get_user_by_id(user_id)
    if user is None:
        raise unauthorized
    return user
