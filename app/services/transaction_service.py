from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException

from app.models.transaction import Transaction
from app.repository.transaction_repository import TransactionRepository
from app.repository.category_repository import CategoryRepository
from app.schemas.transaction_schema import TransactionCreate, TransactionUpdate
from app.transaction_time import moscow_now


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

        category = self.category_repository.get_by_id(data.category_id, user_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        if category.type != data.type:
            raise HTTPException(status_code=400, detail="Тип категории не совпадает с типом транзакции")

        transaction = Transaction(
            user_id=user_id,
            category_id=data.category_id,
            type=data.type,
            amount=data.amount,
            payment_method=data.payment_method,
            description=data.description,
            occurred_at=data.occurred_at.replace(tzinfo=None),
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

    # Проверяет итоговую пару категории и типа до изменения полей.
    def update_transaction(
        self, transaction_id: int, data: TransactionUpdate, user_id: int,
    ) -> Transaction:
        transaction = self.get_transaction(transaction_id, user_id)
        changes = data.model_dump(exclude_unset=True)
        if "category_id" in changes or "type" in changes:
            category = self.category_repository.get_by_id(changes.get("category_id", transaction.category_id), user_id)
            if category is None:
                raise HTTPException(status_code=404, detail="Категория не найдена")
            if category.type != changes.get("type", transaction.type):
                raise HTTPException(status_code=400, detail="Тип категории не совпадает с типом транзакции")
        if "occurred_at" in changes:
            changes["occurred_at"] = changes["occurred_at"].replace(tzinfo=None)
        for name, value in changes.items():
            setattr(transaction, name, value)
        return self.repository.save(transaction)

    def delete_transaction(self, transaction_id: int, user_id: int) -> None:
        transaction = self.get_transaction(transaction_id, user_id)
        self.repository.delete(transaction)

    # Служебная функция. Устанавливает время для выбранного месяца и года.
    def set_time(self, month: int | None, year: int | None):
        now = moscow_now()
        selected_month = now.month if month is None else month
        selected_year = now.year if year is None else year
        start = datetime(selected_year, selected_month, 1)
        if selected_month == 12:
            end = datetime(selected_year + 1, 1, 1)
        else:
            end = datetime(selected_year, selected_month + 1, 1)
        return start, end

    # Возвращает месячный баланс по транзакциям текущего пользователя.
    def get_monthly_balance(self,
                            user_id: int,
                            month: int | None = None,
                            year: int | None = None) -> Decimal:
        start, end = self.set_time(month, year)

        return self.repository.get_balance(user_id, start, end)

    # Возвращает месячный доход по транзакциям текущего пользователя.
    def get_monthly_income(self,
                            user_id: int,
                            month: int | None = None,
                            year: int | None = None) -> Decimal:
        start, end = self.set_time(month, year)

        return self.repository.get_income(user_id, start, end)

    def get_monthly_expense(self,
                            user_id: int,
                            month: int | None = None,
                            year: int | None = None) -> Decimal:
        start, end = self.set_time(month, year)

        return self.repository.get_expences(user_id, start, end)
