"""SMTP delivery or a local .eml outbox; reset links never enter application logs."""
from dataclasses import dataclass
from email.message import EmailMessage
import logging
import os
from pathlib import Path
import smtplib
import ssl
from urllib.parse import urlsplit
from uuid import uuid4

logger = logging.getLogger(__name__)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(repr=False)
class MailSettings:
    mode: str
    sender: str
    host: str
    port: int
    security: str
    username: str
    password: str
    outbox: Path


def get_reset_url() -> str:
    url = os.getenv("PASSWORD_RESET_URL", "http://localhost:5173/reset-password")
    parsed = urlsplit(url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.scheme not in {"http", "https"}
            or (parsed.scheme == "http" and parsed.hostname not in LOOPBACK_HOSTS)):
        raise ValueError("PASSWORD_RESET_URL must be HTTPS (HTTP is allowed for localhost), without query or fragment")
    return url


def get_mail_settings() -> MailSettings:
    mode = os.getenv("MAIL_MODE", "file")
    security = os.getenv("SMTP_SECURITY", "starttls")
    host = os.getenv("SMTP_HOST", "localhost")
    if mode not in {"file", "smtp"} or security not in {"starttls", "ssl", "none"}:
        raise ValueError("Invalid mail configuration")
    if mode == "file" and urlsplit(get_reset_url()).hostname not in LOOPBACK_HOSTS:
        raise ValueError("MAIL_MODE=file is only available for a local frontend")
    if mode == "smtp" and security == "none" and host not in LOOPBACK_HOSTS:
        raise ValueError("Unencrypted SMTP is only allowed for a local mail catcher")
    return MailSettings(
        mode=mode, sender=os.getenv("MAIL_FROM", "Finance Tracker <no-reply@localhost>"),
        host=host, port=int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587")),
        security=security, username=os.getenv("SMTP_USERNAME", ""), password=os.getenv("SMTP_PASSWORD", ""),
        outbox=Path(__file__).resolve().parents[1] / ".local" / "mail",
    )


def send_mail(settings: MailSettings, recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if settings.mode == "file":
        settings.outbox.mkdir(parents=True, exist_ok=True)
        path = settings.outbox / f"{uuid4().hex}.eml"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(message.as_bytes())
        return
    context = ssl.create_default_context()
    smtp_type = smtplib.SMTP_SSL if settings.security == "ssl" else smtplib.SMTP
    options = {"context": context} if settings.security == "ssl" else {}
    with smtp_type(settings.host, settings.port, timeout=10, **options) as client:
        if settings.security == "starttls":
            client.starttls(context=context)
        if settings.username:
            client.login(settings.username, settings.password)
        client.send_message(message)


def deliver_mail(settings: MailSettings, recipient: str, subject: str, body: str) -> None:
    try:
        send_mail(settings, recipient, subject, body)
    except Exception:
        # Не выводим адрес, тело письма, SMTP credentials или токен.
        logger.error("Password recovery email delivery failed")
