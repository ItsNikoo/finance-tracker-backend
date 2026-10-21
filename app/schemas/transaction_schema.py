from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

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


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: int | None = Field(default=None, gt=0)
    type: TransactionType | None = None
    payment_method: PaymentMethod | None = None
    description: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False,
    )
    occurred_at: datetime | None = Field(default=None, description="Дата совершения (МСК).")

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        return to_moscow(value) if value is not None else None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Передайте хотя бы одно поле для изменения")
        for name in self.model_fields_set - {"description"}:
            if getattr(self, name) is None:
                raise ValueError(f"Поле {name} не может быть null")
        return self


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
