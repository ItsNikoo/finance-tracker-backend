from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.models.transaction import TransactionType, PaymentMethod
from app.transaction_time import moscow_now, to_moscow


# Проверяет данные новой транзакции.
class TransactionCreate(BaseModel):
    category_id: int = Field(gt=0)
    type: TransactionType
    payment_method: PaymentMethod
    description: str | None = Field(default=None, max_length=255)
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        allow_inf_nan=False,
    )
    occurred_at: datetime = Field(
        default_factory=moscow_now,
        description="Дата совершения. Без часового пояса — МСК; со смещением — переводится в МСК.",
    )

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return to_moscow(value)


class TransactionDateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime = Field(description="Новая дата совершения транзакции (МСК).")

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return to_moscow(value)


# Описывает транзакцию в ответе API.
class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    type: TransactionType
    payment_method: PaymentMethod
    description: str | None
    amount: Decimal
    created_at: datetime
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return to_moscow(value)
