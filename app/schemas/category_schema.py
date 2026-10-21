from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.transaction import TransactionType


# Проверяет данные для создания категории.
class CategoryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name_en: str = Field(min_length=1, max_length=100)
    name_ru: str = Field(min_length=1, max_length=100)
    type: TransactionType


# Описывает категорию в ответе API.
class CategoryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name_en: str | None = Field(default=None, min_length=1, max_length=100)
    name_ru: str | None = Field(default=None, min_length=1, max_length=100)
    type: TransactionType | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set:
            raise ValueError("Передайте хотя бы одно поле для изменения")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Поля категории не могут быть null")
        return self


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_en: str
    name_ru: str
    type: TransactionType
    is_default: bool
