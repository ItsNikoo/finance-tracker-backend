from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import Transaction


class TransactionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, transaction: Transaction) -> Transaction:
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)

        return transaction

    def get_list(self, user_id: int) -> list[Transaction]:
        statement = select(Transaction).where(Transaction.user_id == user_id)

        transactions = self.db.execute(statement)

        return list(transactions.scalars().all())

    # Ищет транзакцию только среди записей указанного пользователя.
    def get_by_id(self, transaction_id: int, user_id: int) -> Transaction | None:
        statement = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user_id,
        )

        transaction = self.db.execute(statement)

        return transaction.scalar_one_or_none()
