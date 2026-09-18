from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.transaction import TransactionType


# Выполняет запросы к таблице категорий.
class CategoryRepository:
    # Принимает сессию текущего запроса.
    def __init__(self, db: Session):
        self.db = db

    # Сохраняет новую категорию.
    def create(self, category: Category) -> Category:
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    # Возвращает категории в порядке создания.
    def get_list(self) -> list[Category]:
        return list(self.db.scalars(select(Category).order_by(Category.id)).all())

    # Ищет категорию по идентификатору.
    def get_by_id(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)

    # Проверяет совпадение любого названия внутри типа.
    def get_duplicate(
        self, category_type: TransactionType, name_en: str, name_ru: str,
    ) -> Category | None:
        statement = select(Category).where(
            Category.type == category_type,
            or_(Category.name_en == name_en, Category.name_ru == name_ru),
        ).limit(1)
        return self.db.scalar(statement)
