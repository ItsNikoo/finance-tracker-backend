from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.repository.category_repository import CategoryRepository
from app.schemas.category_schema import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.category_service import CategoryService


# Собирает сервис категорий для текущего запроса.
def get_category_service(db: Session = Depends(get_db)) -> CategoryService:
    return CategoryService(CategoryRepository(db))


router = APIRouter(prefix="/categories", tags=["categories"])


# Возвращает общие и личные категории текущего пользователя.
@router.get("", response_model=list[CategoryRead])
def get_categories(service: CategoryService = Depends(get_category_service),
                   user: User = Depends(get_current_user)):
    return service.get_categories(user.id)


# Возвращает одну категорию по идентификатору.
@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, service: CategoryService = Depends(get_category_service),
                   user: User = Depends(get_current_user)):
    return service.get_category(category_id, user.id)


# Создаёт личную категорию.
@router.post("", response_model=CategoryRead, status_code=201)
def create_category(data: CategoryCreate, service: CategoryService = Depends(get_category_service),
                   user: User = Depends(get_current_user)):
    return service.create_category(data, user.id)


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, data: CategoryUpdate,
                    service: CategoryService = Depends(get_category_service),
                    user: User = Depends(get_current_user)):
    return service.update_category(category_id, data, user.id)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, service: CategoryService = Depends(get_category_service),
                    user: User = Depends(get_current_user)):
    service.delete_category(category_id, user.id)
    return Response(status_code=204)
