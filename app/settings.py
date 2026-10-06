import os
from pathlib import Path

from dotenv import load_dotenv


# Загружает настройки из корня проекта без вывода секретов.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

ACCESS_TOKEN_SECONDS = 15 * 60
SESSION_SECONDS = 7 * 24 * 60 * 60
ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"


# Возвращает точные адреса доверенных клиентов.
def get_allowed_origins() -> list[str]:
    origins = [value.strip().rstrip("/") for value in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8000",
    ).split(",") if value.strip()]
    if not origins or "*" in origins or "null" in origins:
        raise RuntimeError("ALLOWED_ORIGINS должен содержать точные адреса клиентов")
    return origins


# Включает защищённые cookies для HTTPS по настройке окружения.
def cookies_are_secure() -> bool:
    return os.getenv("COOKIE_SECURE", "false").lower() == "true"
