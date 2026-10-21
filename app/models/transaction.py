from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Numeric, DateTime, Enum as SqlEnum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.transaction_time import moscow_db_now


# Определяет направление движения денег.
class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"

class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"

# Хранит транзакцию с обязательной категорией.
class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_user_occurred_at", "user_id", "occurred_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"), nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_transactions_user_id_users"), nullable=False, index=True,
    )
    type: Mapped[TransactionType] = mapped_column(
        SqlEnum(TransactionType),
        nullable=False,
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        SqlEnum(PaymentMethod),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=moscow_db_now,
    )
