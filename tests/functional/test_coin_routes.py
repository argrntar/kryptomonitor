"""
Testy funkcjonalne coin_routes.

Testują endpointy HTTP:
    GET /coins/              – lista monet
    GET /coins/<id>          – szczegóły monety
    GET /coins/<id>/history  – AJAX historia cen
"""
import json
import pytest
from app.models.coin import Coin
from app.models.price_history import PriceHistory
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Fixtures pomocnicze
# ---------------------------------------------------------------------------

@pytest.fixture
def coin(db):
    """Moneta testowa w bazie."""
    c = Coin(
        coingecko_id="bitcoin",
        symbol="BTC",
        name="Bitcoin",
        current_price_usd=68_000.0,
        market_cap=1_300_000_000_000.0,
        price_change_24h=2.5,
        last_updated=datetime.now(timezone.utc),
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def coin_with_history(db, coin):
    """Moneta z 5 punktami historii cen."""
    now = datetime.now(timezone.utc)
    for i in range(5):
        db.session.add(PriceHistory(
            coin=coin,
            price_usd=68_000.0 + i * 100,
            recorded_at=now - timedelta(hours=i),
        ))
    db.session.commit()
    return coin


# ---------------------------------------------------------------------------
# GET /coins/
# ---------------------------------------------------------------------------

def test_lista_monet_bez_danych(client):
    """Lista monet ładuje się nawet gdy baza jest pusta."""
    response = client.get("/coins/")
    assert response.status_code == 200


def test_lista_monet_z_danymi(client, coin):
    """Lista monet wyświetla monety z bazy."""
    response = client.get("/coins/")
    assert response.status_code == 200
    assert "Bitcoin" in response.data.decode("utf-8")


# ---------------------------------------------------------------------------
# GET /coins/<id>
# ---------------------------------------------------------------------------

def test_szczegoly_monety_istnieje(client, coin):
    """Strona szczegółów istniejącej monety ładuje się poprawnie."""
    response = client.get(f"/coins/{coin.id}")
    assert response.status_code == 200
    assert "Bitcoin" in response.data.decode("utf-8")


def test_szczegoly_monety_nie_istnieje(client, db):
    """Nieistniejące id monety zwraca 404."""
    response = client.get("/coins/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /coins/<id>/history
# ---------------------------------------------------------------------------

def test_history_api_poprawny_zakres(client, coin_with_history):
    """Historia dla poprawnego zakresu zwraca JSON z listą punktów."""
    response = client.get(f"/coins/{coin_with_history.id}/history?range=30d")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)


def test_history_api_bledny_zakres(client, coin):
    """Nieprawidłowy zakres zwraca 400."""
    response = client.get(f"/coins/{coin.id}/history?range=nieznany")
    assert response.status_code == 400


def test_history_api_nieistniejaca_moneta(client, db):
    """Historia dla nieistniejącej monety zwraca 404."""
    response = client.get("/coins/99999/history?range=30d")
    assert response.status_code == 404


def test_history_api_struktura_odpowiedzi(client, coin_with_history):
    """Każdy punkt historii ma wymagane pola: ts, label, price."""
    response = client.get(f"/coins/{coin_with_history.id}/history?range=30d")
    data = json.loads(response.data)

    if len(data) > 0:
        punkt = data[0]
        assert "ts" in punkt
        assert "label" in punkt
        assert "price" in punkt
