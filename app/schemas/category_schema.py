from pydantic import BaseModel, ConfigDict, Field

from app.models.transaction import TransactionType


# Проверяет данные для создания категории.
class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name_en: str = Field(min_length=1, max_length=100)
    name_ru: str = Field(min_length=1, max_length=100)
    type: TransactionType


# Описывает категорию в ответе API.
class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_en: str
    name_ru: str
    type: TransactionType
