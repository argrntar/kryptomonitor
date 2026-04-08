"""
Testy funkcjonalne portfolio_routes.

Testują endpointy HTTP:
    GET  /portfolio/               – dashboard portfela
    GET  /portfolio/history        – pełna historia transakcji
    GET  /portfolio/history/export – eksport CSV
    POST /portfolio/close-all      – zamknięcie wszystkich pozycji
"""
import pytest
from app.models.coin import Coin
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fixtures pomocnicze
# ---------------------------------------------------------------------------

@pytest.fixture
def coin(db):
    c = Coin(
        coingecko_id="bitcoin",
        symbol="BTC",
        name="Bitcoin",
        current_price_usd=68_000.0,
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def holding(db, user, coin):
    """Otwarta pozycja portfelowa usera testowego."""
    h = Portfolio(
        user_id=user.id,
        coin_id=coin.id,
        amount=0.01,
        avg_buy_price=60_000.0,
    )
    db.session.add(h)
    db.session.commit()
    return h


@pytest.fixture
def transaction(db, user, coin):
    """Jedna transakcja kupna w historii."""
    tx = Transaction(
        user_id=user.id,
        coin_id=coin.id,
        transaction_type="buy",
        amount=0.01,
        price_usd=60_000.0,
        total_usd=600.0,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(tx)
    db.session.commit()
    return tx


# ---------------------------------------------------------------------------
# GET /portfolio/
# ---------------------------------------------------------------------------

def test_dashboard_wymaga_logowania(client):
    """Niezalogowany user jest przekierowywany na login."""
    response = client.get("/portfolio/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_dashboard_pusty_portfel(logged_in_client):
    """Dashboard ładuje się dla usera bez pozycji."""
    response = logged_in_client.get("/portfolio/")
    assert response.status_code == 200
    assert "portfel" in response.data.decode("utf-8").lower()


def test_dashboard_z_pozycja(logged_in_client, holding, coin):
    """Dashboard wyświetla otwartą pozycję."""
    response = logged_in_client.get("/portfolio/")
    assert response.status_code == 200
    assert "BTC" in response.data.decode("utf-8")


# ---------------------------------------------------------------------------
# GET /portfolio/history
# ---------------------------------------------------------------------------

def test_historia_wymaga_logowania(client):
    """Niezalogowany user jest przekierowywany na login."""
    response = client.get("/portfolio/history")
    assert response.status_code == 302


def test_historia_pusta(logged_in_client):
    """Historia bez transakcji ładuje się poprawnie."""
    response = logged_in_client.get("/portfolio/history")
    assert response.status_code == 200


def test_historia_z_transakcja(logged_in_client, transaction):
    """Historia wyświetla transakcje."""
    response = logged_in_client.get("/portfolio/history")
    assert response.status_code == 200
    assert "BTC" in response.data.decode("utf-8")


def test_historia_paginacja_strona_1(logged_in_client):
    """Paginacja – strona 1 ładuje się poprawnie."""
    response = logged_in_client.get("/portfolio/history?page=1")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /portfolio/history/export
# ---------------------------------------------------------------------------

def test_export_csv_wymaga_logowania(client):
    """Niezalogowany user jest przekierowywany."""
    response = client.get("/portfolio/history/export")
    assert response.status_code == 302


def test_export_csv_pusty(logged_in_client):
    """Eksport pustej historii zwraca plik CSV z nagłówkami."""
    response = logged_in_client.get("/portfolio/history/export")
    assert response.status_code == 200
    assert response.content_type == "text/csv; charset=utf-8"
    content = response.data.decode("utf-8")
    assert "Data" in content
    assert "Typ" in content
    assert "Symbol" in content


def test_export_csv_z_transakcja(logged_in_client, transaction):
    """Eksport z transakcjami zawiera dane w CSV."""
    response = logged_in_client.get("/portfolio/history/export")
    content = response.data.decode("utf-8")
    assert "BTC" in content
    assert "KUP" in content


def test_export_csv_wartosc_kupna_ujemna(logged_in_client, transaction):
    """Wartość kupna w CSV jest ujemna."""
    response = logged_in_client.get("/portfolio/history/export")
    content = response.data.decode("utf-8")
    # Transakcja kupna $600 powinna być jako -600.00
    assert "-600.00" in content


# ---------------------------------------------------------------------------
# POST /portfolio/close-all
# ---------------------------------------------------------------------------

def test_close_all_wymaga_logowania(client):
    """Niezalogowany user jest przekierowywany."""
    response = client.post("/portfolio/close-all")
    assert response.status_code == 302


def test_close_all_pusty_portfel(logged_in_client):
    """Zamknięcie pustego portfela – komunikat info."""
    response = logged_in_client.post("/portfolio/close-all",
                                     follow_redirects=True)
    assert response.status_code == 200
    assert "Brak pozycji" in response.data.decode("utf-8")


def test_close_all_z_pozycja(logged_in_client, holding, coin):
    """Zamknięcie otwartej pozycji – komunikat sukces."""
    response = logged_in_client.post("/portfolio/close-all",
                                     follow_redirects=True)
    assert response.status_code == 200
    assert "Zamknięto" in response.data.decode("utf-8")
