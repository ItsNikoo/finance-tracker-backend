from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Numeric, DateTime, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TransactionType] = mapped_column(
        SqlEnum(TransactionType),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now
    )
