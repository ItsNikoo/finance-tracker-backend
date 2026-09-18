from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict

from app.models.transaction import TransactionType


# Проверяет данные новой транзакции.
class TransactionCreate(BaseModel):
    category_id: int = Field(gt=0)
    type: TransactionType
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        allow_inf_nan=False,
    )


# Описывает транзакцию в ответе API.
class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    type: TransactionType
    amount: Decimal
    created_at: datetime
