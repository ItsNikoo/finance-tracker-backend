import secrets
import logging
from urllib.parse import urlencode

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.mailer import deliver_mail, get_mail_settings, get_reset_url
from app.repository.password_reset_repository import PasswordResetRepository
from app.repository.user_repository import UserRepository
from app.security import hash_password, hash_token

logger = logging.getLogger(__name__)


def issue_reset_email(bind, email, settings, url):
    # Поиск аккаунта и доставка выполняются после ответа: HTTP-ответ не ждёт
    # SMTP и не отличается по выполненной работе для существующего email.
    try:
        token = secrets.token_urlsafe(32)
        with Session(bind=bind) as db:
            user = UserRepository(db).get_user_by_email(email)
            if user is None:
                return
            PasswordResetRepository(db).issue(user.id, hash_token(token))
        link = url + "#" + urlencode({"token": token})
        deliver_mail(settings, email, "Восстановление пароля Finance Tracker",
                     f"Для установки нового пароля откройте ссылку:\n\n{link}\n\n"
                     "Ссылка действует 30 минут и может быть использована один раз. "
                     "Если вы не запрашивали восстановление, проигнорируйте письмо.")
    except Exception:
        logger.error("Password recovery request processing failed")


class PasswordResetService:
    def __init__(self, repository: PasswordResetRepository):
        self.repository = repository

    def mail_configuration(self):
        try:
            return get_mail_settings(), get_reset_url()
        except ValueError as exc:
            raise HTTPException(503, "Сервис восстановления пароля не настроен") from exc

    def forgot(self, email: str, ip: str, tasks: BackgroundTasks) -> None:
        settings, url = self.mail_configuration()
        if not self.repository.allow_request("forgot-ip", ip, 20, 3600):
            raise HTTPException(429, "Слишком много запросов. Повторите позже.", headers={"Retry-After": "3600"})
        if not self.repository.allow_request("forgot-email", email, 3, 3600):
            return
        tasks.add_task(issue_reset_email, self.repository.db.get_bind(), email, settings, url)

    def reset(self, token: str, new_password: str, ip: str, tasks: BackgroundTasks) -> None:
        settings, _ = self.mail_configuration()
        if not self.repository.allow_request("reset-ip", ip, 30, 900):
            raise HTTPException(429, "Слишком много запросов. Повторите позже.", headers={"Retry-After": "900"})
        email = self.repository.reset(hash_token(token), hash_password(new_password))
        if email is None:
            raise HTTPException(400, "Ссылка недействительна или устарела. Запросите новую.")
        tasks.add_task(deliver_mail, settings, email, "Пароль Finance Tracker изменён",
                       "Ваш пароль изменён. Все предыдущие сеансы завершены. "
                       "Если это сделали не вы, восстановите пароль и проверьте доступ к вашей почте.")
