def test_register_success(register):
    response = register()

    assert response.status_code == 201, response.text
    assert response.json()["email"] == "example@mail.ru"


def test_register_duplicate_email(register):
    first_response = register()
    assert first_response.status_code == 201, first_response.text

    response = register(
        email="example@mail.ru",
        password="password2"
    )

    assert response.status_code == 409, response.text


def test_register_invalid_email(register):
    response = register(
        email="invalid-email",
        password="password"
    )

    assert response.status_code == 422, response.text


def test_login(register, login, client):
    registered = register()
    assert registered.status_code == 201, registered.text

    response = login()

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "example@mail.ru"

    profile = client.get("/api/users/me")
    assert profile.status_code == 200, profile.text
    assert profile.json()["id"] == registered.json()["id"]


def test_login_unknown_email(register, login, client):
    registered = register()
    assert registered.status_code == 201, registered.text
    response = login("abracadabra@gmail.com", "password")

    assert response.status_code == 401, response.text

    profile = client.get("/api/users/me")
    assert profile.status_code == 401, profile.text


def test_login_invalid_password(register, login, client):
    registered = register()
    assert registered.status_code == 201, registered.text
    response = login("example@mail.ru", "wrongpassword")

    assert response.status_code == 401, response.text

    profile = client.get("/api/users/me")
    assert profile.status_code == 401, profile.text


def test_register_short_password(register):
    response = register(password="short")

    assert response.status_code == 422, response.text


def test_register_does_not_return_password(register):
    response = register()
    assert response.status_code == 201, response.text

    user = response.json()
    assert "password" not in user
    assert "hashed_password" not in user


def test_me_requires_login(client):
    response = client.get("/api/users/me")

    assert response.status_code == 401, response.text


def test_logout(register, login, client, csrf_headers):
    registered = register()
    assert registered.status_code == 201, registered.text
    logged_in = login()
    assert logged_in.status_code == 200, logged_in.text

    profile = client.get("/api/users/me")
    assert profile.status_code == 200, profile.text

    response = client.post("/api/users/logout", headers=csrf_headers())
    assert response.status_code == 204, response.text

    profile = client.get("/api/users/me")
    assert profile.status_code == 401, profile.text


def test_register_requires_csrf(client):
    response = client.post(
        "/api/users/register",
        json={"email": "example@mail.ru", "password": "password"},
    )

    assert response.status_code == 403, response.text
