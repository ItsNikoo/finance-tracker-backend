import pytest


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_other_user_cannot_access_category(
    create_category, authorized_client, second_authorized_client, csrf_headers, method,
):
    created = create_category()
    assert created.status_code == 201, created.text
    original = created.json()
    path = f'/api/categories/{original["id"]}'

    # Второй пользователь не видит личную категорию даже в списке.
    categories = second_authorized_client.get("/api/categories")
    assert categories.status_code == 200, categories.text
    assert original["id"] not in [item["id"] for item in categories.json()]

    if method == "GET":
        response = second_authorized_client.get(path)
    elif method == "PATCH":
        response = second_authorized_client.patch(
            path, json={"name_ru": "Чужое изменение"},
            headers=csrf_headers(second_authorized_client),
        )
    else:
        response = second_authorized_client.delete(path, headers=csrf_headers(second_authorized_client))

    assert response.status_code == 404, response.text
    # Владелец по-прежнему видит исходную категорию.
    assert authorized_client.get(path).json() == original


@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
def test_other_user_cannot_access_transaction(
    create_transaction, authorized_client, second_authorized_client, csrf_headers, method,
):
    created = create_transaction()
    assert created.status_code == 200, created.text
    original = created.json()
    path = f'/api/transactions/{original["id"]}'
    response = second_authorized_client.get("/api/transactions")
    assert response.status_code == 200, response.text
    assert response.json() == []

    if method == "GET":
        response = second_authorized_client.get(path)
    elif method == "PATCH":
        response = second_authorized_client.patch(
            path, json={"amount": "999"}, headers=csrf_headers(second_authorized_client),
        )
    else:
        response = second_authorized_client.delete(path, headers=csrf_headers(second_authorized_client))

    assert response.status_code == 404, response.text
    assert authorized_client.get(path).json() == original


def test_other_user_cannot_use_private_category(
    create_category, second_authorized_client, transaction_data, csrf_headers,
):
    created = create_category(type="expense")
    assert created.status_code == 201, created.text
    private_category_id = created.json()["id"]
    data = transaction_data.copy()
    data["category_id"] = private_category_id

    response = second_authorized_client.post(
        "/api/transactions", json=data, headers=csrf_headers(second_authorized_client),
    )
    assert response.status_code == 404, response.text

    # Даже свою операцию нельзя перенести в чужую личную категорию.
    created = second_authorized_client.post(
        "/api/transactions", json=transaction_data, headers=csrf_headers(second_authorized_client),
    )
    assert created.status_code == 200, created.text
    original = created.json()
    path = f'/api/transactions/{original["id"]}'
    response = second_authorized_client.patch(
        path, json={"category_id": private_category_id},
        headers=csrf_headers(second_authorized_client),
    )
    assert response.status_code == 404, response.text
    assert second_authorized_client.get(path).json() == original


def test_users_can_create_same_category_names(create_category, second_authorized_client, csrf_headers):
    first = create_category()
    assert first.status_code == 201, first.text
    second = second_authorized_client.post(
        "/api/categories",
        json={"name_en": "Test Category", "name_ru": "Тестовая категория", "type": "income"},
        headers=csrf_headers(second_authorized_client),
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]


def test_shared_categories_available_to_both_users(authorized_client, second_authorized_client):
    first = authorized_client.get("/api/categories")
    second = second_authorized_client.get("/api/categories")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    shared = [item for item in first.json() if item["is_default"]]
    assert shared
    assert second.json() == shared
    response = second_authorized_client.get(f'/api/categories/{shared[0]["id"]}')
    assert response.status_code == 200, response.text
    assert response.json() == shared[0]
