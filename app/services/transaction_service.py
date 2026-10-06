from fastapi import HTTPException

from app.models.transaction import Transaction
from app.repository.transaction_repository import TransactionRepository
from app.repository.category_repository import CategoryRepository
from app.schemas.transaction_schema import TransactionCreate


# Проверяет правила создания и получения транзакций.
class TransactionService:
    # Принимает репозитории одной сессии.
    def __init__(self, repository: TransactionRepository, category_repository: CategoryRepository):
        self.repository = repository
        self.category_repository = category_repository

    # Проверяет категорию и сохраняет транзакцию.
    def create_transaction(self, data: TransactionCreate, user_id: int) -> Transaction:
        # тут проверки и бизнес-логика
        if data.amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Транзакция дохода должна быть положительной"
            )

        category = self.category_repository.get_by_id(data.category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        if category.type != data.type:
            raise HTTPException(status_code=400, detail="Тип категории не совпадает с типом транзакции")

        transaction = Transaction(
            user_id=user_id,
            category_id=data.category_id,
            type=data.type,
            amount=data.amount
        )

        return self.repository.create(transaction)

    # Возвращает список транзакций текущего пользователя.
    def get_transactions(self, user_id: int) -> list[Transaction]:
        return self.repository.get_list(user_id)

    # Возвращает транзакцию или ошибку отсутствия.
    def get_transaction(self, transaction_id: int, user_id: int) -> Transaction:
        transaction = self.repository.get_by_id(transaction_id, user_id)

        if transaction is None:
            raise HTTPException(
                status_code=404,
                detail="Транзакция не найдена"
            )

        return transaction
