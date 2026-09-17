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

    def get_list(self) -> list[Transaction]:
        statement = select(Transaction)

        transactions = self.db.execute(statement)

        return list(transactions.scalars().all())

    def get_by_id(self, transaction_id: int) -> Transaction | None:
        statement = select(Transaction).where(Transaction.id == transaction_id)

        transaction = self.db.execute(statement)

        return transaction.scalar_one_or_none()
