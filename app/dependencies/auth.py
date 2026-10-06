import secrets

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.repository.session_repository import SessionRepository
from app.repository.user_repository import UserRepository
from app.security import decode_csrf_token
from app.services.session_service import SessionService
from app.settings import ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE, get_allowed_origins


# Собирает сервис сессий для текущего запроса.
def get_session_service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(SessionRepository(db), UserRepository(db))


# Находит сессию для CSRF и выхода, включая истёкший access.
def get_cookie_session(request: Request, service: SessionService) -> UserSession | None:
    return (service.from_refresh(request.cookies.get(REFRESH_COOKIE))
            or service.from_access(request.cookies.get(ACCESS_COOKIE)))


# Проверяет источник изменяющего запросa по точному списку адресов.
def check_origin(request: Request) -> None:
    if request.headers.get("origin") not in get_allowed_origins():
        raise HTTPException(403, "Источник запроса не разрешён")


# Защищает изменяющие запросы, включая вход, подписанным CSRF-токеном.
def require_csrf(
    request: Request,
    service: SessionService = Depends(get_session_service),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    check_origin(request)
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or not cookie or not secrets.compare_digest(header.encode(), cookie.encode()):
        raise HTTPException(403, "Некорректный CSRF-токен")
    try:
        session_id = decode_csrf_token(header)
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(403, "Некорректный CSRF-токен") from exc
    session = get_cookie_session(request, service)
    expected = session.id if session is not None else "anonymous"
    if session_id != expected:
        raise HTTPException(403, "Обновите CSRF-токен")


# Проверяет access-cookie и возвращает владельца действующей сессии.
def get_current_user(
    request: Request,
    service: SessionService = Depends(get_session_service),
) -> User:
    session = service.from_access(request.cookies.get(ACCESS_COOKIE))
    if session is None:
        raise HTTPException(401, "Не удалось подтвердить пользователя")
    return service.users.get_user_by_id(session.user_id)
