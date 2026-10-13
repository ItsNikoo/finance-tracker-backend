from fastapi import Depends, APIRouter, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repository.transaction_repository import TransactionRepository
from app.repository.category_repository import CategoryRepository
from app.schemas.transaction_schema import TransactionCreate, TransactionRead, TransactionDateUpdate
from app.services.transaction_service import TransactionService


# Собирает сервис с репозиториями текущего запроса.
def get_transaction_service(
        db: Session = Depends(get_db),
) -> TransactionService:
    repository = TransactionRepository(db)
    return TransactionService(repository, CategoryRepository(db))


router = APIRouter(prefix="/transactions", tags=["transactions"])


# Возвращает список транзакций с категориями.
@router.get("", response_model=list[TransactionRead])
def get_transactions(
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_transactions(current_user.id)


# Возвращает баланс выбранного или текущего месяца по дате совершения в МСК.
@router.get("/balance", response_model=float)
def get_monthly_balance(
        month: int | None = Query(default=None, ge=1, le=12, description="Месяц текущего года по МСК. По умолчанию — текущий месяц."),
        year: int | None = Query(default=None, ge=2020, le=2100, description="Год по МСК. По умолчанию — текущий год."),
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_monthly_balance(current_user.id, month, year)

# Возвращает доход выбранного или текущего месяца по дате совершения в МСК.
@router.get("/balance/income", response_model=float)
def get_monthly_income(
        month: int | None = Query(default=None, ge=1, le=12, description="Месяц текущего года по МСК. По умолчанию — текущий месяц."),
        year: int | None = Query(default=None, ge=2020, le=2100, description="Год по МСК. По умолчанию — текущий год."),
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_monthly_income(current_user.id, month, year)

# Возвращает расходы выбранного или текущего месяца по дате совершения в МСК.
@router.get("/balance/expenses", response_model=float)
def get_monthly_expense(
        month: int | None = Query(default=None, ge=1, le=12, description="Месяц текущего года по МСК. По умолчанию — текущий месяц."),
        year: int | None = Query(default=None, ge=2020, le=2100, description="Год по МСК. По умолчанию — текущий год."),
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_monthly_expense(current_user.id, month, year)

# Возвращает транзакцию по идентификатору.
@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction_by_id(
        transaction_id: int,
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_transaction(transaction_id, current_user.id)


# Создаёт транзакцию с выбранной категорией.
@router.post("", response_model=TransactionRead)
def create_transaction(
        data: TransactionCreate,
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.create_transaction(data, current_user.id)


# Изменяет дату совершения транзакции текущего пользователя.
@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction_date(
        transaction_id: int,
        data: TransactionDateUpdate,
        current_user: User = Depends(get_current_user),
        service: TransactionService = Depends(get_transaction_service)
):
    return service.update_transaction_date(transaction_id, data, current_user.id)
