from fastapi import Response

from app.models.user_session import UserSession
from app.security import utc_now
from app.settings import ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE, ACCESS_TOKEN_SECONDS, cookies_are_secure


# Устанавливает cookie только для хоста API.
def set_cookie(response: Response, name: str, value: str, lifetime: int) -> None:
    response.set_cookie(name, value, max_age=lifetime, path="/", httponly=True,
                        secure=cookies_are_secure(), samesite="lax")
    response.headers["Cache-Control"] = "no-store"


# Сохраняет токены входа в недоступных JavaScript cookies.
def set_auth_cookies(response: Response, session: UserSession, access: str, refresh: str) -> None:
    remaining = max(0, int((session.expires_at - utc_now()).total_seconds()))
    set_cookie(response, ACCESS_COOKIE, access, min(ACCESS_TOKEN_SECONDS, remaining))
    set_cookie(response, REFRESH_COOKIE, refresh, remaining)


# Удаляет cookies с теми же параметрами пути и безопасности.
def clear_auth_cookies(response: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=cookies_are_secure(),
                               httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
