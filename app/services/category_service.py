from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.category import Category
from app.repository.category_repository import CategoryRepository
from app.schemas.category_schema import CategoryCreate, CategoryUpdate


# Проверяет правила работы с категориями.
class CategoryService:
    # Принимает репозиторий категорий.
    def __init__(self, repository: CategoryRepository):
        self.repository = repository

    # Создаёт категорию без повторяющихся названий внутри типа.
    def create_category(self, data: CategoryCreate, user_id: int) -> Category:
        if self.repository.get_duplicate(data.type, data.name_en, data.name_ru, user_id):
            raise HTTPException(409, "Категория с таким названием и типом уже существует")
        category = Category(name_en=data.name_en, name_ru=data.name_ru, type=data.type, user_id=user_id)
        try:
            return self.repository.create(category)
        except IntegrityError as exc:
            self.repository.db.rollback()
            # Учитывает одновременное создание одинаковых категорий.
            raise HTTPException(409, "Категория с таким названием и типом уже существует") from exc

    # Возвращает общие и личные категории пользователя.
    def get_categories(self, user_id: int) -> list[Category]:
        return self.repository.get_list(user_id)

    # Возвращает категорию или сообщает об её отсутствии.
    def get_category(self, category_id: int, user_id: int) -> Category:
        category = self.repository.get_by_id(category_id, user_id)
        if category is None:
            raise HTTPException(404, "Категория не найдена")
        return category

    def get_owned_category(self, category_id: int, user_id: int) -> Category:
        category = self.get_category(category_id, user_id)
        if category.is_default:
            raise HTTPException(403, "Общие категории нельзя изменять или удалять")
        return category

    def update_category(self, category_id: int, data: CategoryUpdate, user_id: int) -> Category:
        category = self.get_owned_category(category_id, user_id)
        changes = data.model_dump(exclude_unset=True)
        category_type = changes.get("type", category.type)
        if category_type != category.type and self.repository.is_used(category.id):
            raise HTTPException(409, "Нельзя изменить тип категории, используемой в транзакциях")
        if self.repository.get_duplicate(category_type, changes.get("name_en", category.name_en),
                                         changes.get("name_ru", category.name_ru), user_id, category.id):
            raise HTTPException(409, "Категория с таким названием и типом уже существует")
        for name, value in changes.items():
            setattr(category, name, value)
        try:
            return self.repository.save(category)
        except IntegrityError as exc:
            self.repository.db.rollback()
            raise HTTPException(409, "Категория с таким названием и типом уже существует") from exc

    def delete_category(self, category_id: int, user_id: int) -> None:
        category = self.get_owned_category(category_id, user_id)
        replacement = self.repository.get_default_other(category.type)
        if replacement is None:
            raise HTTPException(409, "Общая категория «Прочее» для этого типа не найдена")
        try:
            self.repository.delete(category, replacement)
        except IntegrityError as exc:
            self.repository.db.rollback()
            raise HTTPException(409, "Не удалось удалить категорию и перенести транзакции") from exc
