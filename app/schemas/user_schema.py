from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# Проверяет данные для создания пользователя.
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, repr=False)

    # Приводит email к единому регистру для хранения и поиска.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


# Описывает публичные данные пользователя.
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    created_at: datetime


# Проверяет данные для входа пользователя.
class UserLogin(BaseModel):
    email: EmailStr
    password: str

    # Приводит email к единому регистру для хранения и поиска.
    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


# Возвращает CSRF-токен для последующих запросов клиента.
class CsrfRead(BaseModel):
    csrf_token: str


# Возвращает профиль и CSRF-токен после входа или обновления сессии.
class AuthRead(CsrfRead):
    user: UserRead


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$", repr=False)
    new_password: str = Field(min_length=8, max_length=128, repr=False)


class ForgotPasswordResponse(BaseModel):
    message: str = "Если аккаунт существует, мы отправили инструкцию по восстановлению пароля."
