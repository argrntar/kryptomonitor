"""
Testy funkcjonalne auth_routes.

Testują endpointy HTTP:
    GET/POST /auth/register
    GET/POST /auth/login
    GET      /auth/logout
    GET/POST /auth/profile
    POST     /auth/delete-account
"""


# ---------------------------------------------------------------------------
# /auth/register
# ---------------------------------------------------------------------------

def test_register_get_zwraca_formularz(client):
    """Strona rejestracji ładuje się poprawnie."""
    response = client.get("/auth/register")
    assert response.status_code == 200
    assert "Zarejestruj" in response.data.decode("utf-8")


def test_register_post_sukces(client, db):
    """Poprawna rejestracja tworzy konto i przekierowuje."""
    response = client.post("/auth/register", data={
        "username": "nowyuser",
        "email": "nowy@test.com",
        "password": "haslo12345",
        "password_confirm": "haslo12345",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Witaj" in response.data.decode("utf-8")


def test_register_post_hasla_rozne(client, db):
    """Różne hasła – formularz wraca z błędem walidacji."""
    response = client.post("/auth/register", data={
        "username": "nowyuser",
        "email": "nowy@test.com",
        "password": "haslo12345",
        "password_confirm": "inne_haslo",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "identyczne" in response.data.decode("utf-8")


def test_register_post_zduplikowany_username(client, db, user):
    """Zajęty username – formularz wraca z błędem."""
    response = client.post("/auth/register", data={
        "username": "testuser",  # już istnieje
        "email": "inny@test.com",
        "password": "haslo12345",
        "password_confirm": "haslo12345",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "zajęta" in response.data.decode("utf-8")


def test_register_zalogowany_przekierowany(logged_in_client):
    """Zalogowany user próbujący wejść na rejestrację jest przekierowywany."""
    response = logged_in_client.get("/auth/register")
    assert response.status_code == 302


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------

def test_login_get_zwraca_formularz(client):
    """Strona logowania ładuje się poprawnie."""
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert "Zaloguj" in response.data.decode("utf-8")


def test_login_post_sukces(client, user):
    """Poprawne dane logują i przekierowują na listę monet."""
    response = client.post("/auth/login", data={
        "username": "testuser",
        "password": "password123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Witaj, testuser" in response.data.decode("utf-8")


def test_login_post_zle_haslo(client, user):
    """Błędne hasło – komunikat o błędzie."""
    response = client.post("/auth/login", data={
        "username": "testuser",
        "password": "zle_haslo",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Nieprawidłowa" in response.data.decode("utf-8")


def test_login_post_nieistniejacy_user(client, db):
    """Nieistniejący username – komunikat o błędzie."""
    response = client.post("/auth/login", data={
        "username": "nieistnieje",
        "password": "cokolwiek",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Nieprawidłowa" in response.data.decode("utf-8")


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------

def test_logout_wylogowuje(logged_in_client):
    """Wylogowanie przekierowuje na stronę logowania."""
    response = logged_in_client.get("/auth/logout", follow_redirects=True)
    assert response.status_code == 200
    assert "Zostałeś wylogowany" in response.data.decode("utf-8")


def test_logout_wymaga_logowania(client):
    """Niezalogowany user próbujący wylogować się – redirect na login."""
    response = client.get("/auth/logout")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# /auth/profile
# ---------------------------------------------------------------------------

def test_profile_wymaga_logowania(client):
    """Niezalogowany user – redirect na login."""
    response = client.get("/auth/profile")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_profile_get_zalogowany(logged_in_client):
    """Zalogowany user widzi stronę profilu."""
    response = logged_in_client.get("/auth/profile")
    assert response.status_code == 200
    assert "testuser" in response.data.decode("utf-8")


def test_profile_post_zmiana_danych(logged_in_client, db):
    """Zmiana username i email zapisuje się poprawnie."""
    response = logged_in_client.post("/auth/profile", data={
        "username": "zmieniony_nick",
        "email": "zmieniony@test.com",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "zaktualizowany" in response.data.decode("utf-8")


# ---------------------------------------------------------------------------
# /auth/delete-account
# ---------------------------------------------------------------------------

def test_delete_account_get_niedozwolony(logged_in_client):
    """Endpoint delete-account nie obsługuje GET – 405 Method Not Allowed."""
    response = logged_in_client.get("/auth/delete-account")
    assert response.status_code == 405


def test_delete_account_zle_haslo(logged_in_client, db):
    """Błędne hasło – konto nie zostaje usunięte."""
    response = logged_in_client.post("/auth/delete-account", data={
        "confirm_password": "zle_haslo",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Nieprawidłowe hasło" in response.data.decode("utf-8")


def test_delete_account_sukces(logged_in_client, db):
    """Poprawne hasło i brak pozycji – konto zostaje usunięte."""
    response = logged_in_client.post("/auth/delete-account", data={
        "confirm_password": "password123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "usunięte" in response.data.decode("utf-8")
