from sqlalchemy import case, or_, select, update
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.transaction import TransactionType, Transaction


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

    # Возвращает категории в порядке создания, помещая «Прочее» в конец.
    def get_list(self, user_id: int) -> list[Category]:
        return list(self.db.scalars(select(Category).where(
            or_(Category.user_id.is_(None), Category.user_id == user_id),
        ).order_by(case((Category.name_ru == "Прочее", 1), else_=0), Category.id)).all())

    # Ищет категорию по идентификатору.
    def get_by_id(self, category_id: int, user_id: int) -> Category | None:
        return self.db.scalar(select(Category).where(
            Category.id == category_id,
            or_(Category.user_id.is_(None), Category.user_id == user_id),
        ))

    # Проверяет совпадение любого названия внутри типа.
    def get_duplicate(
        self, category_type: TransactionType, name_en: str, name_ru: str,
        user_id: int, exclude_id: int | None = None,
    ) -> Category | None:
        statement = select(Category).where(
            Category.type == category_type,
            Category.user_id == user_id,
            or_(Category.name_en == name_en, Category.name_ru == name_ru),
        ).limit(1)
        if exclude_id is not None:
            statement = statement.where(Category.id != exclude_id)
        return self.db.scalar(statement)

    def is_used(self, category_id: int) -> bool:
        return self.db.scalar(select(Transaction.id).where(
            Transaction.category_id == category_id,
        ).limit(1)) is not None

    def save(self, category: Category) -> Category:
        self.db.commit()
        self.db.refresh(category)
        return category

    def get_default_other(self, category_type: TransactionType) -> Category | None:
        return self.db.scalar(select(Category).where(
            Category.user_id.is_(None),
            Category.type == category_type,
            Category.name_ru == "Прочее",
        ))

    # Переносит операции и удаляет категорию одной транзакцией БД.
    def delete(self, category: Category, replacement: Category) -> None:
        self.db.execute(update(Transaction).where(
            Transaction.category_id == category.id,
            Transaction.user_id == category.user_id,
        ).values(category_id=replacement.id))
        self.db.delete(category)
        self.db.commit()
