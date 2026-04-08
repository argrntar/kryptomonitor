"""
Testy jednostkowe auth_service.

Testują logikę biznesową serwisu w izolacji:
    - register()        – tworzenie konta
    - authenticate()    – weryfikacja logowania
    - update_profile()  – edycja danych i hasła
    - delete_account()  – usuwanie konta z walidacją pozycji
"""
from app.services import auth_service
from app.models.coin import Coin
from app.models.portfolio import Portfolio


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------

def test_register_tworzy_usera(db):
    """Rejestracja zwraca obiekt User z uzupełnionym id."""
    user = auth_service.register("jan", "jan@test.com", "haslo123")
    assert user.id is not None
    assert user.username == "jan"
    assert user.email == "jan@test.com"
    assert user.balance_usd == 10_000.0


def test_register_hashuje_haslo(db):
    """Hasło nie jest przechowywane jako plain text."""
    user = auth_service.register("jan", "jan@test.com", "haslo123")
    assert user.password_hash != "haslo123"
    assert len(user.password_hash) > 20


def test_register_dwa_rozne_konta(db):
    """Można zarejestrować dwa różne konta."""
    u1 = auth_service.register("jan", "jan@test.com", "haslo123")
    u2 = auth_service.register("anna", "anna@test.com", "haslo456")
    assert u1.id != u2.id


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------

def test_authenticate_poprawne_dane(db, user):
    """Poprawne dane logowania zwracają obiekt User."""
    result = auth_service.authenticate("testuser", "password123")
    assert result is not None
    assert result.id == user.id


def test_authenticate_zle_haslo(db, user):
    """Błędne hasło zwraca None."""
    result = auth_service.authenticate("testuser", "zle_haslo")
    assert result is None


def test_authenticate_nieistniejacy_user(db):
    """Nieistniejący username zwraca None."""
    result = auth_service.authenticate("nieistnieje", "cokolwiek")
    assert result is None


# ---------------------------------------------------------------------------
# update_profile()
# ---------------------------------------------------------------------------

def test_update_profile_zmienia_dane(db, user):
    """Zmiana username i email zapisuje się w bazie."""
    success, msg = auth_service.update_profile(
        user=user,
        username="nowy_nick",
        email="nowy@test.com",
    )
    assert success is True
    assert user.username == "nowy_nick"
    assert user.email == "nowy@test.com"


def test_update_profile_zmiana_hasla(db, user):
    """Zmiana hasła wymaga podania aktualnego hasła."""
    success, msg = auth_service.update_profile(
        user=user,
        username="testuser",
        email="test@example.com",
        current_password="password123",
        new_password="nowe_haslo456",
    )
    assert success is True
    # Nowe hasło powinno działać przy logowaniu
    result = auth_service.authenticate("testuser", "nowe_haslo456")
    assert result is not None


def test_update_profile_zle_aktualne_haslo(db, user):
    """Błędne aktualne hasło blokuje zmianę."""
    success, msg = auth_service.update_profile(
        user=user,
        username="testuser",
        email="test@example.com",
        current_password="zle_haslo",
        new_password="nowe_haslo456",
    )
    assert success is False
    assert "nieprawidłowe" in msg.lower()


# ---------------------------------------------------------------------------
# delete_account()
# ---------------------------------------------------------------------------

def test_delete_account_sukces_bez_pozycji(db, user):
    """Usunięcie konta bez otwartych pozycji – sukces."""
    success, msg = auth_service.delete_account(user, "password123")
    assert success is True


def test_delete_account_zle_haslo(db, user):
    """Błędne hasło blokuje usunięcie."""
    success, msg = auth_service.delete_account(user, "zle_haslo")
    assert success is False
    assert "hasło" in msg.lower()


def test_delete_account_blokada_gdy_sa_pozycje(db, user):
    """Usunięcie zablokowane gdy user ma otwarte pozycje w portfelu."""
    # Dodaj monetę i pozycję portfelową
    coin = Coin(coingecko_id="bitcoin", symbol="BTC",
                name="Bitcoin", current_price_usd=68000.0)
    db.session.add(coin)
    db.session.flush()

    holding = Portfolio(
        user_id=user.id,
        coin_id=coin.id,
        amount=0.01,
        avg_buy_price=60000.0,
    )
    db.session.add(holding)
    db.session.commit()

    success, msg = auth_service.delete_account(user, "password123")
    assert success is False
    assert "BTC" in msg


def test_delete_account_mozliwe_po_wyzerowaniu_pozycji(db, user):
    """Po wyzerowaniu amount pozycji usunięcie jest możliwe."""
    coin = Coin(coingecko_id="bitcoin", symbol="BTC",
                name="Bitcoin", current_price_usd=68000.0)
    db.session.add(coin)
    db.session.flush()

    holding = Portfolio(
        user_id=user.id,
        coin_id=coin.id,
        amount=0.0,  # ← wyzerowane
        avg_buy_price=60000.0,
    )
    db.session.add(holding)
    db.session.commit()

    success, msg = auth_service.delete_account(user, "password123")
    assert success is True
