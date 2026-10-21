from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction, TransactionType


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, transaction: Transaction) -> Transaction:
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)

        return transaction

    def save(self, transaction: Transaction) -> Transaction:
        self.db.commit()
        self.db.refresh(transaction)
        return transaction

    def delete(self, transaction: Transaction) -> None:
        self.db.delete(transaction)
        self.db.commit()

    def get_list(self, user_id: int) -> list[Transaction]:
        statement = select(Transaction).where(Transaction.user_id == user_id)

        transactions = self.db.execute(statement)

        return list(transactions.scalars().all())

    # Считает доходы минус расходы за период с исключённой верхней границей.
    def get_balance(self, user_id: int, start: datetime, end: datetime) -> Decimal:
        signed_amount = case(
            (Transaction.type == TransactionType.INCOME, Transaction.amount),
            else_=-Transaction.amount,
        )
        statement = select(func.coalesce(func.sum(signed_amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )

        return self.db.execute(statement).scalar_one()

    # Считает доходы за период с исключённой верхней границей.
    def get_income(self, user_id: int, start: datetime, end: datetime) -> Decimal:
        statement = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.INCOME,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )

        return self.db.execute(statement).scalar_one()

    # Считает расходы за период с исключенной верхней границей.
    def get_expences(self, user_id: int, start: datetime, end: datetime) -> Decimal:
        statement = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )

        return self.db.execute(statement).scalar_one()

    # Ищет транзакцию только среди записей указанного пользователя.
    def get_by_id(self, transaction_id: int, user_id: int) -> Transaction | None:
        statement = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )

        transaction = self.db.execute(statement)

        return transaction.scalar_one_or_none()
