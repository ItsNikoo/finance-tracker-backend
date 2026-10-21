import pytest


# Создание транзакции
def test_create_transaction_success(authorized_client, csrf_headers, transaction_data):
    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 200, response.text

    # Проверяем не только ответ создания, но и сохранённые данные.
    transaction = response.json()
    assert transaction["amount"] == "100.00"
    assert transaction["category_id"] == transaction_data["category_id"]
    assert transaction["type"] == "expense"
    assert transaction["payment_method"] == "cash"
    assert transaction["description"] == "Test transaction"
    saved = authorized_client.get(f'/api/transactions/{transaction["id"]}')
    assert saved.status_code == 200, saved.text
    assert saved.json() == transaction


def test_create_transaction_invalid_category(authorized_client, csrf_headers):
    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": 9999,  # Не существующая категория
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction with invalid category",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 404, response.text  # Ожидаем ошибку 404 для несуществующей категории

def test_create_transaction_incorrect_category(authorized_client, csrf_headers):
    create_category = authorized_client.post(
        "/api/categories",
        json={
            "name_en": "Test Category",
            "name_ru": "Категория для дохода",
            "type": "income"
        },
        headers=csrf_headers()
    )

    assert create_category.status_code == 201, create_category.text
    category_id = create_category.json()["id"]

    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": category_id,  # Категория типа "income"
            "type": "expense",  # Попытка создать транзакцию типа "expense"
            "payment_method": "cash",
            "description": "Test transaction with incorrect category type",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 400, response.text  # Ожидаем ошибку 400 для некорректного типа категории

@pytest.mark.parametrize("amount", ["0", "-50.00", "1.001"])
def test_create_transaction_invalid_amount(authorized_client, csrf_headers, transaction_data, amount):
    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction with invalid amount",
            "amount": amount,  # Неверная сумма
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 422, response.text  # Нулевая, отрицательная или слишком точная сумма недопустима.


def test_create_transaction_missing_fields(authorized_client, csrf_headers):
    response = authorized_client.post(
        "/api/transactions",
        json={
            # Пропущено поле category_id
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction with missing fields",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 422, response.text  # Ожидаем ошибку валидации для отсутствующих обязательных полей


def test_create_transaction_invalid_type(authorized_client, csrf_headers, transaction_data):
    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "invalid_type",  # Неверный тип транзакции
            "payment_method": "cash",
            "description": "Test transaction with invalid type",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 422, response.text  # Ожидаем ошибку валидации для неверного типа транзакции


def test_create_transaction_invalid_payment_method(authorized_client, csrf_headers, transaction_data):
    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "invalid_method",  # Неверный метод оплаты
            "description": "Test transaction with invalid payment method",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )


    assert response.status_code == 422, response.text  # Ожидаем ошибку валидации для неверного метода оплаты


def test_create_transaction_invalid_occurred_at(authorized_client, csrf_headers, transaction_data):
    response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction with invalid occurred_at",
            "amount": 100.00,
            "occurred_at": "invalid_date"  # Неверный формат даты
        },
        headers=csrf_headers()
    )


    assert response.status_code == 422, response.text  # Ожидаем ошибку валидации для неверного формата даты


# GET-запросы
def test_get_transaction_by_id_success(authorized_client, csrf_headers, transaction_data):
    # Сначала создаем транзакцию
    create_response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )

    assert create_response.status_code == 200, create_response.text
    transaction_id = create_response.json()["id"]

    # Теперь получаем транзакцию по ID
    response = authorized_client.get(
        f"/api/transactions/{transaction_id}"
    )


    assert response.status_code == 200, response.text
    assert response.json()["id"] == transaction_id

def test_get_transaction_by_id_not_found(authorized_client):
    response = authorized_client.get(
        "/api/transactions/9999"  # Не существующий ID транзакции
    )


    assert response.status_code == 404, response.text  # Ожидаем ошибку 404 для несуществующей транзакции

def test_get_transactions_list(authorized_client, csrf_headers, transaction_data):
    create_response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )

    assert create_response.status_code == 200, create_response.text
    response = authorized_client.get(
        "/api/transactions"
    )


    assert response.status_code == 200, response.text
    transactions = response.json()
    assert isinstance(transactions, list)
    assert len(transactions) == 1
    assert transactions[0]["description"] == "Test transaction"

# PATCH-запросы
def test_update_transaction_success(authorized_client, csrf_headers, transaction_data):
    # Сначала создаем транзакцию
    create_response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )

    assert create_response.status_code == 200, create_response.text
    transaction_id = create_response.json()["id"]

    # Теперь обновляем транзакцию
    update_response = authorized_client.patch(
        f"/api/transactions/{transaction_id}",
        json={
            "description": "Updated transaction",
            "amount": 150.0
        },
        headers=csrf_headers()
    )


    assert update_response.status_code == 200, update_response.text
    updated_transaction = update_response.json()
    assert updated_transaction["description"] == "Updated transaction"
    assert updated_transaction["type"] == "expense"
    assert updated_transaction["amount"] == "150.00"
    # При изменении суммы и описания остальные поля остаются прежними.
    original = create_response.json()
    for field in ("id", "category_id", "type", "payment_method", "occurred_at", "created_at"):
        assert updated_transaction[field] == original[field]
    saved = authorized_client.get(f"/api/transactions/{transaction_id}")
    assert saved.status_code == 200, saved.text
    assert saved.json() == updated_transaction

# DELETE-запросы
def test_delete_transaction_success(authorized_client, csrf_headers, transaction_data):
    # Сначала создаем транзакцию
    create_response = authorized_client.post(
        "/api/transactions",
        json={
            "category_id": transaction_data["category_id"],
            "type": "expense",
            "payment_method": "cash",
            "description": "Test transaction",
            "amount": 100.00,
            "occurred_at": "2026-06-01T12:00:00"
        },
        headers=csrf_headers()
    )

    assert create_response.status_code == 200, create_response.text
    transaction_id = create_response.json()["id"]

    # Теперь удаляем транзакцию
    delete_response = authorized_client.delete(
        f"/api/transactions/{transaction_id}",
        headers=csrf_headers()
    )


    assert delete_response.status_code == 204, delete_response.text

    # Проверяем, что транзакция больше не существует
    get_response = authorized_client.get(
        f"/api/transactions/{transaction_id}"
    )

    assert get_response.status_code == 404, get_response.text

def test_delete_transaction_not_found(authorized_client, csrf_headers):
    delete_response = authorized_client.delete(
        "/api/transactions/9999",  # Не существующий ID транзакции
        headers=csrf_headers()
    )


    assert delete_response.status_code == 404, delete_response.text  # Ожидаем ошибку 404 для несуществующей транзакции


def test_transactions_require_login(client, csrf_headers):
    response = client.get("/api/transactions")
    assert response.status_code == 401, response.text

    # CSRF правильный: отказ должен быть именно из-за отсутствия входа.
    response = client.post(
        "/api/transactions",
        json={"category_id": 1, "type": "expense", "payment_method": "cash", "amount": "10"},
        headers=csrf_headers(),
    )
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("changes", [{}, {"amount": "0"}, {"amount": "1.001"}, {"user_id": 999}])
def test_update_transaction_invalid_data(create_transaction, authorized_client, csrf_headers, changes):
    created = create_transaction()
    assert created.status_code == 200, created.text
    original = created.json()
    path = f'/api/transactions/{original["id"]}'

    response = authorized_client.patch(path, json=changes, headers=csrf_headers())
    assert response.status_code == 422, response.text
    # Ошибка проверки не должна частично менять операцию.
    assert authorized_client.get(path).json() == original
