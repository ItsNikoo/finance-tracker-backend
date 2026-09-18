from sqlalchemy import Enum as SqlEnum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.transaction import TransactionType


# Хранит общую категорию доходов или расходов.
class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("type", "name_en", name="uq_category_type_name_en"),
        UniqueConstraint("type", "name_ru", name="uq_category_type_name_ru"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name_en: Mapped[str] = mapped_column(String(100))
    name_ru: Mapped[str] = mapped_column(String(100))
    type: Mapped[TransactionType] = mapped_column(SqlEnum(TransactionType))
