from fastapi import Depends, APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.repository.transaction_repository import TransactionRepository
from app.schemas.transaction_schema import TransactionCreate
from app.services.transaction_service import TransactionService


def get_transaction_service(
        db: Session = Depends(get_db),
) -> TransactionService:
    repository = TransactionRepository(db)
    return TransactionService(repository)


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def get_transactions(
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_transactions()


@router.get("/{transaction_id}")
def get_transaction_by_id(
        transaction_id: int,
        service: TransactionService = Depends(get_transaction_service)
):
    return service.get_transaction(transaction_id)


@router.post("")
def create_transaction(
        data: TransactionCreate,
        service: TransactionService = Depends(get_transaction_service)
):
    return service.create_transaction(data)
