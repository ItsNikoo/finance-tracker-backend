import pytest


def test_category_create_successful(create_category):
    response = create_category()

    assert response.status_code == 201


def test_category_create_invalid_name(create_category):
    response = create_category(name_en="")

    assert response.status_code == 422


def test_category_create_invalid_type(create_category):
    response = create_category(type="invalid_type")

    assert response.status_code == 422


def test_category_create_duplicate(create_category):
    response1 = create_category()

    assert response1.status_code == 201

    response2 = create_category()

    assert response2.status_code == 409


def test_get_categories(authorized_client):
    response = authorized_client.get("/api/categories")

    assert response.status_code == 200

    categories = response.json()

    assert isinstance(categories, list)
    assert len(categories) > 0

    category = categories[0]

    assert "id" in category
    assert "name_en" in category
    assert "name_ru" in category
    assert "type" in category
    assert "is_default" in category


def test_get_category_by_id_success(create_category, authorized_client):
    create_response = create_category()

    assert create_response.status_code == 201

    category_id = create_response.json()["id"]

    response = authorized_client.get(
        f"/api/categories/{category_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == category_id


def test_get_category_by_id_not_found(authorized_client):
    response = authorized_client.get(
        "/api/categories/9999"
    )

    assert response.status_code == 404


def test_update_category_success(create_category, authorized_client, csrf_headers):
    create_response = create_category()

    assert create_response.status_code == 201

    category_id = create_response.json()["id"]

    update_data = {
        "name_en": "Updated Category",
        "name_ru": "Обновленная категория",
        "type": "expense"
    }

    response = authorized_client.patch(
        f"/api/categories/{category_id}",
        headers=csrf_headers(),
        json=update_data
    )

    assert response.status_code == 200
    updated_category = response.json()
    assert updated_category["name_en"] == update_data["name_en"]
    assert updated_category["name_ru"] == update_data["name_ru"]
    assert updated_category["type"] == update_data["type"]


def test_delete_category_success(create_category, authorized_client, csrf_headers):
    create_response = create_category()

    assert create_response.status_code == 201

    category_id = create_response.json()["id"]

    response = authorized_client.delete(
        f"/api/categories/{category_id}",
        headers=csrf_headers()
    )

    assert response.status_code == 204

    # Проверяем, что категория действительно удалена.
    get_response = authorized_client.get(
        f"/api/categories/{category_id}"
    )
    assert get_response.status_code == 404


def test_shared_category_cannot_be_changed_or_deleted(authorized_client, csrf_headers):
    categories = authorized_client.get("/api/categories")
    assert categories.status_code == 200, categories.text
    category = next(item for item in categories.json() if item["is_default"])
    path = f'/api/categories/{category["id"]}'

    updated = authorized_client.patch(path, json={"name_ru": "Новое имя"}, headers=csrf_headers())
    assert updated.status_code == 403, updated.text
    deleted = authorized_client.delete(path, headers=csrf_headers())
    assert deleted.status_code == 403, deleted.text
    assert authorized_client.get(path).json() == category


def test_other_categories_are_last(authorized_client, create_category):
    # Новая личная категория тоже должна оказаться перед «Прочее».
    created = create_category()
    assert created.status_code == 201, created.text
    response = authorized_client.get("/api/categories")
    assert response.status_code == 200, response.text
    for category_type in ("income", "expense"):
        categories = [item for item in response.json() if item["type"] == category_type]
        assert categories[-1]["name_ru"] == "Прочее"


def test_category_partial_update(create_category, authorized_client, csrf_headers):
    created = create_category()
    assert created.status_code == 201, created.text
    original = created.json()
    path = f'/api/categories/{original["id"]}'
    response = authorized_client.patch(path, json={"name_ru": "Новое имя"}, headers=csrf_headers())
    assert response.status_code == 200, response.text
    assert response.json() == {**original, "name_ru": "Новое имя"}
    assert authorized_client.get(path).json() == response.json()


def test_used_category_can_be_renamed_but_cannot_change_type(
    create_category, create_transaction, authorized_client, csrf_headers,
):
    category = create_category(type="expense")
    assert category.status_code == 201, category.text
    operation = create_transaction(category_id=category.json()["id"])
    assert operation.status_code == 200, operation.text
    path = f'/api/categories/{category.json()["id"]}'

    response = authorized_client.patch(path, json={"type": "income"}, headers=csrf_headers())
    assert response.status_code == 409, response.text
    assert authorized_client.get(path).json() == category.json()
    response = authorized_client.patch(path, json={"name_ru": "Переименованная"}, headers=csrf_headers())
    assert response.status_code == 200, response.text
    assert response.json()["name_ru"] == "Переименованная"
    saved = authorized_client.get(f'/api/transactions/{operation.json()["id"]}')
    assert saved.json() == operation.json()


@pytest.mark.parametrize("category_type", ["income", "expense"])
def test_delete_category_moves_operations_to_other(
    create_category, create_transaction, authorized_client, csrf_headers, category_type,
):
    category = create_category(type=category_type)
    assert category.status_code == 201, category.text
    categories = authorized_client.get("/api/categories")
    assert categories.status_code == 200, categories.text
    replacement = next(item for item in categories.json()
                       if item["is_default"] and item["type"] == category_type and item["name_ru"] == "Прочее")
    originals = []
    for amount in ("10.25", "20.50"):
        created = create_transaction(category_id=category.json()["id"], type=category_type, amount=amount)
        assert created.status_code == 200, created.text
        originals.append(created.json())
    params = {"month": 6, "year": 2026}
    balance = authorized_client.get("/api/transactions/balance", params=params)
    assert balance.status_code == 200, balance.text

    deleted = authorized_client.delete(f'/api/categories/{category.json()["id"]}', headers=csrf_headers())
    assert deleted.status_code == 204, deleted.text
    assert authorized_client.get(f'/api/categories/{category.json()["id"]}').status_code == 404
    # Меняется только категория: операции и все остальные поля сохраняются.
    for original in originals:
        saved = authorized_client.get(f'/api/transactions/{original["id"]}')
        assert saved.status_code == 200, saved.text
        assert saved.json() == {**original, "category_id": replacement["id"]}
    operations = authorized_client.get("/api/transactions")
    assert operations.status_code == 200, operations.text
    assert len(operations.json()) == 2
    assert authorized_client.get("/api/transactions/balance", params=params).json() == balance.json()


@pytest.mark.parametrize("names", [
    {"name_en": "Test Category", "name_ru": "Другое имя"},
    {"name_en": "Different name", "name_ru": "Тестовая категория"},
])
def test_category_duplicate_one_name(create_category, names):
    created = create_category()
    assert created.status_code == 201, created.text
    response = create_category(**names)
    assert response.status_code == 409, response.text
