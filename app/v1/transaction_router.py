from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repository.transaction_repository import TransactionRepository
from app.repository.category_repository import CategoryRepository
from app.schemas.transaction_schema import TransactionCreate, TransactionRead
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
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_transactions()


# Возвращает транзакцию по идентификатору.
@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction_by_id(
        transaction_id: int,
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_transaction(transaction_id)


# Создаёт транзакцию с выбранной категорией.
@router.post("", response_model=TransactionRead)
def create_transaction(
        data: TransactionCreate,
        service: TransactionService = Depends(get_transaction_service)
):
    return service.create_transaction(data)
