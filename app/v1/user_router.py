import jwt
from fastapi import BackgroundTasks, Depends, APIRouter, Request, Response
from sqlalchemy.orm import Session

from app.cookies import clear_auth_cookies, set_auth_cookies, set_cookie
from app.database import get_db
from app.dependencies.auth import (
    get_current_user, get_session_service, get_cookie_session, check_origin,
)
from app.models.user import User
from app.repository.user_repository import UserRepository
from app.schemas.user_schema import UserRead, UserCreate, UserLogin, CsrfRead, AuthRead
from app.security import create_csrf_token, decode_csrf_token, utc_now
from app.services.user_service import UserService
from app.services.session_service import SessionService
from app.settings import REFRESH_COOKIE, CSRF_COOKIE
from app.schemas.user_schema import ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest
from app.repository.password_reset_repository import PasswordResetRepository
from app.services.password_reset_service import PasswordResetService


# Собирает сервис пользователей для текущего запроса.
def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(UserRepository(db))


router = APIRouter(prefix="/users", tags=["users"])


def get_password_reset_service(db: Session = Depends(get_db)) -> PasswordResetService:
    return PasswordResetService(PasswordResetRepository(db))


@router.post("/forgot-password", status_code=202, response_model=ForgotPasswordResponse)
def forgot_password(data: ForgotPasswordRequest, request: Request, tasks: BackgroundTasks,
                    service: PasswordResetService = Depends(get_password_reset_service)):
    service.forgot(data.email, request.client.host if request.client else "unknown", tasks)
    return ForgotPasswordResponse()


@router.post("/reset-password", status_code=204)
def reset_password(data: ResetPasswordRequest, request: Request, tasks: BackgroundTasks,
                   service: PasswordResetService = Depends(get_password_reset_service)):
    service.reset(data.token, data.new_password, request.client.host if request.client else "unknown", tasks)
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response


# Возвращает действующий CSRF-токен, сохраняя его между вкладками.
@router.get("/csrf", response_model=CsrfRead)
def get_csrf(request: Request, response: Response,
             service: SessionService = Depends(get_session_service)):
    if request.headers.get("origin") is not None:
        check_origin(request)
    session = get_cookie_session(request, service)
    session_id = session.id if session is not None else "anonymous"
    lifetime = max(1, int((session.expires_at - utc_now()).total_seconds())) if session else 3600
    token = request.cookies.get(CSRF_COOKIE, "")
    try:
        valid = decode_csrf_token(token) == session_id
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        valid = False
    if not valid:
        token = create_csrf_token(session_id, lifetime)
    set_cookie(response, CSRF_COOKIE, token, lifetime)
    return CsrfRead(csrf_token=token)


# Возвращает публичные данные текущего пользователя.
@router.get("/me", response_model=UserRead)
def get_me(response: Response, current_user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return current_user


# Создаёт пользователя без автоматического входа.
@router.post("/register", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, service: UserService = Depends(get_user_service)):
    return service.create_user(data)


# Создаёт сессию и устанавливает cookies после успешного входа.
@router.post("/login", response_model=AuthRead)
def login_user(data: UserLogin, request: Request, response: Response,
               service: UserService = Depends(get_user_service),
               sessions: SessionService = Depends(get_session_service)):
    user = service.login_user(data)
    previous = get_cookie_session(request, sessions)
    if previous is not None:
        sessions.revoke(previous)
    session, access, refresh = sessions.create(user.id)
    set_auth_cookies(response, session, access, refresh)
    csrf = create_csrf_token(session.id, max(1, int((session.expires_at - utc_now()).total_seconds())))
    set_cookie(response, CSRF_COOKIE, csrf, max(1, int((session.expires_at - utc_now()).total_seconds())))
    return AuthRead(user=UserRead.model_validate(user), csrf_token=csrf)


# Однократно заменяет refresh-cookie и обновляет access-cookie.
@router.post("/refresh", response_model=AuthRead)
def refresh_session(request: Request, response: Response,
                    service: SessionService = Depends(get_session_service)):
    session, access, refresh = service.refresh(request.cookies.get(REFRESH_COOKIE))
    set_auth_cookies(response, session, access, refresh)
    return AuthRead(user=UserRead.model_validate(service.users.get_user_by_id(session.user_id)),
                    csrf_token=request.headers["x-csrf-token"])


# Отзывает текущую сессию и удаляет cookies даже при истёкшем access.
@router.post("/logout", status_code=204)
def logout_user(request: Request, service: SessionService = Depends(get_session_service)):
    session = get_cookie_session(request, service)
    if session is not None:
        service.revoke(session)
    response = Response(status_code=204)
    clear_auth_cookies(response)
    return response
