from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.repository.category_repository import CategoryRepository
from app.schemas.category_schema import CategoryCreate, CategoryRead
from app.services.category_service import CategoryService


# Собирает сервис категорий для текущего запроса.
def get_category_service(db: Session = Depends(get_db)) -> CategoryService:
    return CategoryService(CategoryRepository(db))


router = APIRouter(prefix="/categories", tags=["categories"])


# Возвращает список общих категорий.
@router.get("", response_model=list[CategoryRead])
def get_categories(service: CategoryService = Depends(get_category_service)):
    return service.get_categories()


# Возвращает одну категорию по идентификатору.
@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, service: CategoryService = Depends(get_category_service)):
    return service.get_category(category_id)


# Создаёт общую категорию.
@router.post("", response_model=CategoryRead, status_code=201)
def create_category(data: CategoryCreate, service: CategoryService = Depends(get_category_service)):
    return service.create_category(data)
