from fastapi import HTTPException

from app.models.transaction import Transaction
from app.repository.transaction_repository import TransactionRepository
from app.schemas.transaction_schema import TransactionCreate


class TransactionService:
    def __init__(self, repository: TransactionRepository):
        self.repository = repository

    def create_transaction(self, data: TransactionCreate) -> Transaction:
        # тут проверки и бизнес-логика
        if data.amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Транзакция дохода должна быть положительной"
            )

        transaction = Transaction(
            type=data.type,
            amount=data.amount
        )

        return self.repository.create(transaction)

    def get_transactions(self) -> list[Transaction]:
        return self.repository.get_list()

    def get_transaction(self, transaction_id: int) -> Transaction:
        transaction = self.repository.get_by_id(transaction_id)

        if transaction is None:
            raise HTTPException(
                status_code=404,
                detail="Транзакция не найдена"
            )

        return transaction
