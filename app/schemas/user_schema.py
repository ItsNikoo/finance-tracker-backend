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
