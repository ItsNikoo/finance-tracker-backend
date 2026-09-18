from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.category import Category
from app.repository.category_repository import CategoryRepository
from app.schemas.category_schema import CategoryCreate


# Проверяет правила работы с категориями.
class CategoryService:
    # Принимает репозиторий категорий.
    def __init__(self, repository: CategoryRepository):
        self.repository = repository

    # Создаёт категорию без повторяющихся названий внутри типа.
    def create_category(self, data: CategoryCreate) -> Category:
        if self.repository.get_duplicate(data.type, data.name_en, data.name_ru):
            raise HTTPException(409, "Категория с таким названием и типом уже существует")
        category = Category(name_en=data.name_en, name_ru=data.name_ru, type=data.type)
        try:
            return self.repository.create(category)
        except IntegrityError as exc:
            # Учитывает одновременное создание одинаковых категорий.
            raise HTTPException(409, "Категория с таким названием и типом уже существует") from exc

    # Возвращает все категории.
    def get_categories(self) -> list[Category]:
        return self.repository.get_list()

    # Возвращает категорию или сообщает об её отсутствии.
    def get_category(self, category_id: int) -> Category:
        category = self.repository.get_by_id(category_id)
        if category is None:
            raise HTTPException(404, "Категория не найдена")
        return category
