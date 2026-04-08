"""
Testy funkcjonalne trade_routes.

Testują endpointy HTTP:
    GET  /trade/<coin_id>       – formularz kupna/sprzedaży
    POST /trade/<coin_id>/buy   – wykonanie zakupu
    POST /trade/<coin_id>/sell  – wykonanie sprzedaży
"""
import pytest
from app.models.coin import Coin
from app.models.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Fixtures pomocnicze
# ---------------------------------------------------------------------------

@pytest.fixture
def coin(db):
    """Moneta testowa z ceną $100."""
    c = Coin(
        coingecko_id="testcoin",
        symbol="TST",
        name="TestCoin",
        current_price_usd=100.0,
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def coin_with_holding(db, user, coin):
    """Moneta + pozycja portfelowa 1 szt dla usera testowego."""
    holding = Portfolio(
        user_id=user.id,
        coin_id=coin.id,
        amount=1.0,
        avg_buy_price=100.0,
    )
    db.session.add(holding)
    db.session.commit()
    return coin


# ---------------------------------------------------------------------------
# GET /trade/<coin_id>
# ---------------------------------------------------------------------------

def test_formularz_wymaga_logowania(client, coin):
    """Niezalogowany user jest przekierowywany na login."""
    response = client.get(f"/trade/{coin.id}")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_formularz_zalogowany(logged_in_client, coin):
    """Zalogowany user widzi formularz kupna/sprzedaży."""
    response = logged_in_client.get(f"/trade/{coin.id}")
    assert response.status_code == 200
    assert "TestCoin" in response.data.decode("utf-8")


def test_formularz_nieistniejaca_moneta(logged_in_client, db):
    """Nieistniejące id monety zwraca 404."""
    response = logged_in_client.get("/trade/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /trade/<coin_id>/buy
# ---------------------------------------------------------------------------

def test_buy_sukces(logged_in_client, coin):
    """Poprawne kupno przekierowuje na dashboard portfela."""
    response = logged_in_client.post(f"/trade/{coin.id}/buy", data={
        "amount": "1.0",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Kupiono" in response.data.decode("utf-8")


def test_buy_brak_srodkow(logged_in_client, coin):
    """Kupno za więcej niż saldo – komunikat o błędzie."""
    response = logged_in_client.post(f"/trade/{coin.id}/buy", data={
        "amount": "200.0",  # 200 * $100 = $20 000 > $10 000 salda
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "Potrzebujesz" in response.data.decode("utf-8")


def test_buy_nieprawidlowa_ilosc(logged_in_client, coin):
    """Zerowa lub ujemna ilość – błąd walidacji formularza."""
    response = logged_in_client.post(f"/trade/{coin.id}/buy", data={
        "amount": "0",
    }, follow_redirects=True)
    assert response.status_code == 200


def test_buy_nieistniejaca_moneta(logged_in_client, db):
    """Kupno nieistniejącej monety zwraca 404."""
    response = logged_in_client.post("/trade/99999/buy", data={
        "amount": "1.0",
    })
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /trade/<coin_id>/sell
# ---------------------------------------------------------------------------

def test_sell_sukces(logged_in_client, coin_with_holding):
    """Sprzedaż posiadanej monety przekierowuje na dashboard."""
    response = logged_in_client.post(
        f"/trade/{coin_with_holding.id}/sell",
        data={"amount": "1.0"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Sprzedano" in response.data.decode("utf-8")


def test_sell_brak_monety(logged_in_client, coin):
    """Sprzedaż monety której user nie posiada – komunikat o błędzie."""
    response = logged_in_client.post(f"/trade/{coin.id}/sell", data={
        "amount": "1.0",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "masz" in response.data.decode("utf-8").lower()


def test_sell_za_duzo(logged_in_client, coin_with_holding):
    """Sprzedaż więcej niż posiadane – komunikat o błędzie."""
    response = logged_in_client.post(
        f"/trade/{coin_with_holding.id}/sell",
        data={"amount": "999.0"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "masz" in response.data.decode("utf-8").lower()
