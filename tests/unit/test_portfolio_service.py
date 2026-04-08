"""
Testy jednostkowe portfolio_service.

Testują logikę biznesową:
    - buy()             – kupno kryptowaluty
    - sell()            – sprzedaż kryptowaluty
    - build_positions() – obliczenia P&L
    - get_min_sell_amount() – minimalna ilość sprzedaży
"""
import pytest
from decimal import Decimal

from app.models.coin import Coin
from app.services import portfolio_service
from app.exceptions import InsufficientFundsError, InsufficientCoinError


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
        market_cap=1_000_000.0,
        price_change_24h=1.5,
    )
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def cheap_coin(db):
    """Tania moneta testowa z ceną $0.09 (np. DOGE)."""
    c = Coin(
        coingecko_id="cheapcoin",
        symbol="CHE",
        name="CheapCoin",
        current_price_usd=0.09,
    )
    db.session.add(c)
    db.session.commit()
    return c


# ---------------------------------------------------------------------------
# buy()
# ---------------------------------------------------------------------------

def test_buy_poprawna_transakcja(db, user, coin):
    """Kupno zmniejsza saldo i tworzy pozycję portfelową."""
    tx = portfolio_service.buy(user, coin, 1.0)

    assert tx is not None
    assert tx.transaction_type == "buy"
    assert tx.amount == 1.0
    assert tx.price_usd == 100.0
    assert tx.total_usd == 100.0
    assert user.balance_usd == 9_900.0


def test_buy_tworzy_holding(db, user, coin):
    """Po kupnie istnieje wpis w portfolio."""
    portfolio_service.buy(user, coin, 2.0)

    from app.repositories import portfolio_repository
    holding = portfolio_repository.find_by_user_and_coin(user.id, coin.id)
    assert holding is not None
    assert holding.amount == 2.0


def test_buy_srednia_wazna_ceny(db, user, coin):
    """Drugie kupno aktualizuje średnią ważoną cenę zakupu."""
    portfolio_service.buy(user, coin, 1.0)  # 1 szt po $100
    coin.current_price_usd = 200.0
    portfolio_service.buy(user, coin, 1.0)  # 1 szt po $200

    from app.repositories import portfolio_repository
    holding = portfolio_repository.find_by_user_and_coin(user.id, coin.id)
    assert holding is not None
    assert holding.avg_buy_price == 150.0


def test_buy_brak_srodkow(db, user, coin):
    """Kupno za więcej niż saldo rzuca InsufficientFundsError."""
    with pytest.raises(InsufficientFundsError):
        portfolio_service.buy(user, coin, 200.0)  # 200 * $100 = $20 000 > $10 000


def test_buy_za_mala_wartosc(db, user, coin):
    """Kupno za mniej niż $0.01 rzuca InsufficientFundsError.

    Przy cenie $1 000 000 minimalna ilość to 0.00001.
    Kupno 0.0001 szt * $1 000 000 = $100 → OK (nie rzuca błędu).
    Kupno 0.000001 szt * $1 000 000 = $1 → OK.
    Dopiero poniżej progu: 0.000000001 * $1 000 000 = $0.001 < $0.01 → błąd.
    Ale AMOUNT_PRECISION = 0.0001 więc testujemy przez cenę $1 000 000
    i ilość 0.0001 → $100 > $0.01 (OK).

    Prawidłowy sposób: bardzo niska cena i minimalna ilość.
    """
    # Cena $0.000001 → 0.0001 szt * $0.000001 = $0.0000000001 < $0.01
    coin.current_price_usd = 0.000001
    db.session.commit()
    with pytest.raises(InsufficientFundsError):
        portfolio_service.buy(user, coin, 0.0001)


# ---------------------------------------------------------------------------
# sell()
# ---------------------------------------------------------------------------

def test_sell_poprawna_transakcja(db, user, coin):
    """Sprzedaż zwiększa saldo i zmniejsza pozycję."""
    portfolio_service.buy(user, coin, 2.0)
    tx = portfolio_service.sell(user, coin, 1.0)

    assert tx.transaction_type == "sell"
    assert tx.amount == 1.0
    # saldo: 10000 - 200 (buy) + 100 (sell) = 9900
    assert user.balance_usd == 9_900.0


def test_sell_brak_monety(db, user, coin):
    """Sprzedaż monety której user nie posiada rzuca InsufficientCoinError."""
    with pytest.raises(InsufficientCoinError):
        portfolio_service.sell(user, coin, 1.0)


def test_sell_za_duzo(db, user, coin):
    """Sprzedaż więcej niż posiadane rzuca InsufficientCoinError."""
    portfolio_service.buy(user, coin, 1.0)
    with pytest.raises(InsufficientCoinError):
        portfolio_service.sell(user, coin, 2.0)


def test_sell_zeruje_resztki(db, user, cheap_coin):
    """Pozostałość poniżej MIN_DUST (0.0001) jest zerowana."""
    portfolio_service.buy(user, cheap_coin, 1.0)

    from app.repositories import portfolio_repository
    holding = portfolio_repository.find_by_user_and_coin(user.id, cheap_coin.id)
    assert holding is not None
    holding.amount = 0.00005  # poniżej MIN_DUST
    db.session.commit()

    portfolio_service.sell(user, cheap_coin, 0.00005)
    assert holding.amount == 0.0


# ---------------------------------------------------------------------------
# build_positions()
# ---------------------------------------------------------------------------

def test_build_positions_zysk(db, user, coin):
    """P&L dodatni gdy aktualna cena > cena zakupu."""
    portfolio_service.buy(user, coin, 1.0)  # kupno po $100
    coin.current_price_usd = 150.0  # cena wzrosła do $150

    from app.repositories import portfolio_repository
    holdings = portfolio_repository.find_by_user(user.id)
    coins_map = {coin.id: coin}

    positions, total_value, total_cost = portfolio_service.build_positions(
        holdings, coins_map
    )

    assert len(positions) == 1
    assert positions[0]["pnl_usd"] == 50.0
    assert positions[0]["is_positive"] is True


def test_build_positions_strata(db, user, coin):
    """P&L ujemny gdy aktualna cena < cena zakupu."""
    portfolio_service.buy(user, coin, 1.0)
    coin.current_price_usd = 80.0

    from app.repositories import portfolio_repository
    holdings = portfolio_repository.find_by_user(user.id)
    coins_map = {coin.id: coin}

    positions, _, _ = portfolio_service.build_positions(holdings, coins_map)

    assert positions[0]["pnl_usd"] == -20.0
    assert positions[0]["is_positive"] is False


def test_build_positions_pomija_zerowe(db, user, coin):
    """Pozycje z amount=0 są pomijane."""
    portfolio_service.buy(user, coin, 1.0)

    from app.repositories import portfolio_repository
    holding = portfolio_repository.find_by_user_and_coin(user.id, coin.id)
    holding.amount = 0.0
    db.session.commit()

    holdings = portfolio_repository.find_by_user(user.id)
    positions, _, _ = portfolio_service.build_positions(holdings, {coin.id: coin})
    assert len(positions) == 0


# ---------------------------------------------------------------------------
# get_min_sell_amount()
# ---------------------------------------------------------------------------

def test_get_min_sell_amount_tania_moneta(db, cheap_coin):
    """Dla taniej monety minimalna ilość jest większa niż 0.0001."""
    min_amount = portfolio_service.get_min_sell_amount(cheap_coin)
    # $0.01 / $0.09 ≈ 0.1112 → zaokrąglone w górę
    assert min_amount is not None
    assert min_amount > Decimal("0.0001")


def test_get_min_sell_amount_droga_moneta(db, coin):
    """Dla monety po $100 minimalna ilość = AMOUNT_PRECISION (0.0001) → zwraca None."""
    # $0.01 / $100 = 0.0001 = AMOUNT_PRECISION → None (brak specjalnego komunikatu)
    result = portfolio_service.get_min_sell_amount(coin)
    assert result is None


def test_get_min_sell_amount_brak_ceny(db):
    """Moneta bez ceny zwraca None."""
    coin_bez_ceny = Coin(
        coingecko_id="nocoin",
        symbol="NOC",
        name="NoCoin",
        current_price_usd=None,
    )
    db.session.add(coin_bez_ceny)
    db.session.commit()

    result = portfolio_service.get_min_sell_amount(coin_bez_ceny)
    assert result is None
