from sqlalchemy import Enum as SqlEnum, String, Index, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.transaction import TransactionType


# Хранит общую или личную категорию доходов или расходов.
class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        *(Index(f"uq_category_default_type_{name}", "type", name, unique=True,
                sqlite_where=text("user_id IS NULL")) for name in ("name_en", "name_ru")),
        *(Index(f"uq_category_user_type_{name}", "user_id", "type", name, unique=True,
                sqlite_where=text("user_id IS NOT NULL")) for name in ("name_en", "name_ru")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    name_en: Mapped[str] = mapped_column(String(100))
    name_ru: Mapped[str] = mapped_column(String(100))
    type: Mapped[TransactionType] = mapped_column(SqlEnum(TransactionType))

    @property
    def is_default(self) -> bool:
        return self.user_id is None
