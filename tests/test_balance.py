def test_empty_balance(authorized_client):
    params = {"month": 6, "year": 2026}
    for path in ("/balance", "/balance/income", "/balance/expenses"):
        response = authorized_client.get("/api/transactions" + path, params=params)
        assert response.status_code == 200, response.text
        assert response.json() == 0


def test_balance_income_minus_expenses(create_category, create_transaction, authorized_client):
    category = create_category(type="income")
    assert category.status_code == 201, category.text
    income = create_transaction(category_id=category.json()["id"], type="income", amount="1000.00")
    expense = create_transaction(amount="250.00")
    assert income.status_code == 200, income.text
    assert expense.status_code == 200, expense.text

    # Проверяем общий баланс и отдельные суммы доходов и расходов.
    params = {"month": 6, "year": 2026}
    for path, expected in (("/balance", 750), ("/balance/income", 1000), ("/balance/expenses", 250)):
        response = authorized_client.get("/api/transactions" + path, params=params)
        assert response.status_code == 200, response.text
        assert response.json() == expected


def test_negative_balance(create_transaction, authorized_client):
    created = create_transaction(amount="250.25")
    assert created.status_code == 200, created.text
    response = authorized_client.get("/api/transactions/balance", params={"month": 6, "year": 2026})
    assert response.status_code == 200, response.text
    assert response.json() == -250.25


def test_balance_does_not_include_other_user(
    create_transaction, authorized_client, second_authorized_client, csrf_headers, transaction_data,
):
    created = create_transaction()
    assert created.status_code == 200, created.text
    other = second_authorized_client.post(
        "/api/transactions", json={**transaction_data, "amount": "999.00"},
        headers=csrf_headers(second_authorized_client),
    )
    assert other.status_code == 200, other.text
    params = {"month": 6, "year": 2026}
    first_balance = authorized_client.get("/api/transactions/balance", params=params)
    second_balance = second_authorized_client.get("/api/transactions/balance", params=params)
    assert first_balance.status_code == 200, first_balance.text
    assert second_balance.status_code == 200, second_balance.text
    assert first_balance.json() == -100
    assert second_balance.json() == -999


def test_balance_month_boundaries(create_transaction, authorized_client):
    # Начало июня включается, начало июля уже относится к другому месяцу.
    for date, amount in (
        ("2026-05-31T23:59:59+03:00", "500"),
        ("2026-06-01T00:00:00+03:00", "10"),
        ("2026-06-30T23:59:59+03:00", "20"),
        ("2026-07-01T00:00:00+03:00", "700"),
    ):
        created = create_transaction(occurred_at=date, amount=amount)
        assert created.status_code == 200, created.text
    response = authorized_client.get("/api/transactions/balance", params={"month": 6, "year": 2026})
    assert response.status_code == 200, response.text
    assert response.json() == -30


def test_balance_december_and_january(create_transaction, authorized_client):
    for date, amount in (("2026-12-31T23:59:59+03:00", "10"), ("2027-01-01T00:00:00+03:00", "20")):
        created = create_transaction(occurred_at=date, amount=amount)
        assert created.status_code == 200, created.text
    december = authorized_client.get("/api/transactions/balance", params={"month": 12, "year": 2026})
    january = authorized_client.get("/api/transactions/balance", params={"month": 1, "year": 2027})
    assert december.status_code == 200, december.text
    assert january.status_code == 200, january.text
    assert december.json() == -10
    assert january.json() == -20


def test_transaction_timezone_changes_balance_month(create_transaction, authorized_client):
    # В UTC ещё май, но по МСК уже июнь.
    created = create_transaction(occurred_at="2026-05-31T21:30:00Z")
    assert created.status_code == 200, created.text
    assert created.json()["occurred_at"] == "2026-06-01T00:30:00+03:00"
    june = authorized_client.get("/api/transactions/balance", params={"month": 6, "year": 2026})
    may = authorized_client.get("/api/transactions/balance", params={"month": 5, "year": 2026})
    assert june.status_code == 200, june.text
    assert may.status_code == 200, may.text
    assert june.json() == -100
    assert may.json() == 0
