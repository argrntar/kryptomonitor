"""
Testy jednostkowe coin_service.

Testują logikę biznesową:
    - update_prices()        – upsert monet, zapis historii, throttling
    - ensure_history()       – uzupełnianie historii z API, throttling
    - cleanup_coin_history() – usuwanie starych punktów, throttling

Kluczowe techniki:
    - monkeypatch       – podmiana funkcji API na fake bez sieci
    - module state reset – czyszczenie _last_update/_ensure_checked/_last_cleanup
                          między testami (zmienne modułu zachowują stan)

Dlaczego monkeypatch zamiast prawdziwego API?
    Testy muszą być szybkie, deterministyczne i działać bez internetu.
    monkeypatch.setattr() podmienia funkcję tylko na czas trwania testu
    i automatycznie przywraca oryginał po zakończeniu.
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.models.coin import Coin
from app.models.price_history import PriceHistory
import app.services.coin_service as coin_service


# ---------------------------------------------------------------------------
# Fixtures pomocnicze
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_module_state():
    """
    Resetuje stan modułu coin_service przed każdym testem.

    coin_service używa zmiennych modułu jako throttling cache:
        _last_update    – kiedy ostatnio odpytano CoinGecko
        _ensure_checked – kiedy ostatnio sprawdzano historię per (coin_id, days)
        _last_cleanup   – kiedy ostatnio czyszczono historię per coin_id

    Bez resetu stan z jednego testu przeciekałby do następnego –
    np. throttling blokowałby wywołanie API w kolejnym teście.

    autouse=True – fixture uruchamia się automatycznie dla każdego testu
    w tym module bez konieczności jawnego podawania jako parametru.
    """
    coin_service._last_update = None
    coin_service._ensure_checked.clear()
    coin_service._last_cleanup.clear()
    yield
    # Po teście też czyścimy – żeby nie wpływać na testy w innych plikach
    coin_service._last_update = None
    coin_service._ensure_checked.clear()
    coin_service._last_cleanup.clear()


@pytest.fixture
def bitcoin(db):
    """Moneta Bitcoin w bazie."""
    c = Coin(
        coingecko_id="bitcoin",
        symbol="BTC",
        name="Bitcoin",
        current_price_usd=60_000.0,
    )
    db.session.add(c)
    db.session.commit()
    return c


# Dane które "zwraca" mock CoinGecko API
FAKE_API_RESPONSE = [
    {
        "id": "bitcoin",
        "symbol": "btc",
        "name": "Bitcoin",
        "current_price": 68_000.0,
        "market_cap": 1_300_000_000_000.0,
        "price_change_percentage_24h": 2.5,
    },
    {
        "id": "ethereum",
        "symbol": "eth",
        "name": "Ethereum",
        "current_price": 2_100.0,
        "market_cap": 250_000_000_000.0,
        "price_change_percentage_24h": -1.2,
    },
]

# Historia cen zwracana przez mock – lista [timestamp_ms, price]
FAKE_HISTORY = [
    [1711929600000.0, 65_000.0],  # 30 dni temu
    [1712016000000.0, 66_000.0],  # 29 dni temu
    [1712102400000.0, 67_000.0],  # 28 dni temu
]


# ---------------------------------------------------------------------------
# update_prices() – throttling
# ---------------------------------------------------------------------------

def test_update_prices_throttling_blokuje(db, monkeypatch):
    """Drugie wywołanie w ciągu 5 minut nie odpytuje API."""
    wywolania = []

    def fake_get_top_coins():
        wywolania.append(1)
        return FAKE_API_RESPONSE

    monkeypatch.setattr("app.api_clients.coingecko_client.get_top_coins", fake_get_top_coins)

    coin_service.update_prices()  # pierwsze – powinno wywołać API
    coin_service.update_prices()  # drugie – powinno być zablokowane przez throttling

    assert len(wywolania) == 1  # API wywołane tylko raz


def test_update_prices_throttling_po_czasie(db, monkeypatch):
    """Po upływie _UPDATE_INTERVAL API jest odpytywane ponownie."""
    wywolania = []

    def fake_get_top_coins():
        wywolania.append(1)
        return FAKE_API_RESPONSE

    monkeypatch.setattr("app.api_clients.coingecko_client.get_top_coins", fake_get_top_coins)

    # Symuluj że ostatnia aktualizacja była 10 minut temu (> 5 min interwału)
    coin_service._last_update = datetime.now(timezone.utc) - timedelta(minutes=10)

    coin_service.update_prices()
    assert len(wywolania) == 1


# ---------------------------------------------------------------------------
# update_prices() – upsert monet
# ---------------------------------------------------------------------------

def test_update_prices_tworzy_nowe_monety(db, monkeypatch):
    """Monety których nie ma w bazie zostają utworzone."""
    monkeypatch.setattr(
        "app.api_clients.coingecko_client.get_top_coins",
        lambda: FAKE_API_RESPONSE,
    )

    coin_service.update_prices()

    from app.repositories import coin_repository
    btc = coin_repository.find_by_coingecko_id("bitcoin")
    eth = coin_repository.find_by_coingecko_id("ethereum")

    assert btc is not None
    assert btc.symbol == "BTC"
    assert btc.current_price_usd == 68_000.0

    assert eth is not None
    assert eth.symbol == "ETH"


def test_update_prices_aktualizuje_istniejaca(db, bitcoin, monkeypatch):
    """Istniejąca moneta ma zaktualizowaną cenę po update."""
    assert bitcoin.current_price_usd == 60_000.0

    monkeypatch.setattr(
        "app.api_clients.coingecko_client.get_top_coins",
        lambda: FAKE_API_RESPONSE,
    )

    coin_service.update_prices()

    db.session.refresh(bitcoin)
    assert bitcoin.current_price_usd == 68_000.0
    assert bitcoin.symbol == "BTC"


def test_update_prices_pomija_bez_id(db, monkeypatch):
    """Monety bez coingecko_id są pomijane."""
    dane_z_brakujacym_id = [
        {"id": None, "symbol": "??", "current_price": 100.0},
        {"symbol": "??", "current_price": 100.0},  # brak klucza id
    ]
    monkeypatch.setattr(
        "app.api_clients.coingecko_client.get_top_coins",
        lambda: dane_z_brakujacym_id,
    )

    coin_service.update_prices()

    from sqlalchemy import select
    from app.models.coin import Coin as CoinModel
    wynik = db.session.execute(select(CoinModel)).scalars().all()
    assert len(wynik) == 0  # nic nie zostało zapisane


def test_update_prices_pomija_bez_ceny(db, monkeypatch):
    """Monety bez current_price są pomijane."""
    dane_bez_ceny = [
        {"id": "testcoin", "symbol": "tst", "name": "Test", "current_price": None},
    ]
    monkeypatch.setattr(
        "app.api_clients.coingecko_client.get_top_coins",
        lambda: dane_bez_ceny,
    )

    coin_service.update_prices()

    from app.repositories import coin_repository
    coin = coin_repository.find_by_coingecko_id("testcoin")
    assert coin is None


# ---------------------------------------------------------------------------
# update_prices() – zapis historii
# ---------------------------------------------------------------------------

def test_update_prices_zapisuje_price_history(db, monkeypatch):
    """Każde wywołanie update_prices dodaje punkt do price_history."""
    monkeypatch.setattr(
        "app.api_clients.coingecko_client.get_top_coins",
        lambda: FAKE_API_RESPONSE,
    )

    coin_service.update_prices()

    from sqlalchemy import select
    historia = db.session.execute(select(PriceHistory)).scalars().all()
    # Dwie monety → dwa punkty historii
    assert len(historia) == 2


# ---------------------------------------------------------------------------
# update_prices() – błąd API
# ---------------------------------------------------------------------------

def test_update_prices_blad_api_nie_crashuje(db, monkeypatch):
    """Błąd połączenia z CoinGecko nie powoduje wyjątku – stare dane zachowane."""

    def rzuc_blad():
        raise ConnectionError("brak sieci")

    monkeypatch.setattr("app.api_clients.coingecko_client.get_top_coins", rzuc_blad)

    # Nie powinno rzucić żadnego wyjątku
    coin_service.update_prices()

    # _last_update NIE powinno być ustawione – błąd = brak aktualizacji
    assert coin_service._last_update is None


# ---------------------------------------------------------------------------
# ensure_history() – throttling
# ---------------------------------------------------------------------------

def test_ensure_history_throttling_blokuje(db, bitcoin, monkeypatch):
    """Drugie wywołanie w ciągu 10 minut nie odpytuje API."""
    wywolania = []

    def fake_get_history(coingecko_id, days):
        wywolania.append(1)
        return FAKE_HISTORY

    monkeypatch.setattr("app.services.coin_service.get_coin_history", fake_get_history)

    coin_service.ensure_history(bitcoin, days=30)  # pierwsze – API wywołane
    coin_service.ensure_history(bitcoin, days=30)  # drugie – zablokowane

    assert len(wywolania) == 1


def test_ensure_history_rozne_zakresy_osobny_throttling(db, bitcoin, monkeypatch):
    """Różne zakresy (30d vs 7d) mają osobny throttling.

    Fake zwraca pustą listę – nie dodajemy punktów do bazy.
    Gdyby fake dodał punkty sprzed 30 dni, wywołanie dla 7d
    znalazłoby wystarczające dane i zrobiło early return bez API.
    """
    wywolania = []

    def fake_get_history(coingecko_id, days):
        wywolania.append(days)
        return []  # pusta lista – baza pozostaje pusta między wywołaniami

    monkeypatch.setattr("app.services.coin_service.get_coin_history", fake_get_history)

    coin_service.ensure_history(bitcoin, days=30)
    coin_service.ensure_history(bitcoin, days=7)

    # Oba zakresy powinny wywołać API osobno
    assert 30 in wywolania
    assert 7 in wywolania


# ---------------------------------------------------------------------------
# ensure_history() – early return gdy mamy dane
# ---------------------------------------------------------------------------

def test_ensure_history_nie_odpytuje_gdy_ma_dane(db, bitcoin, monkeypatch):
    """Jeśli baza ma dane sięgające wystarczająco wstecz – API nie jest odpytywane."""
    wywolania = []

    def fake_get_history(coingecko_id, days):
        wywolania.append(1)
        return FAKE_HISTORY

    monkeypatch.setattr("app.services.coin_service.get_coin_history", fake_get_history)

    # Dodaj punkt historii sprzed 35 dni (sięga poza wymagane 30 dni)
    stary_punkt = datetime.now(timezone.utc) - timedelta(days=35)
    db.session.add(PriceHistory(
        coin=bitcoin,
        price_usd=50_000.0,
        recorded_at=stary_punkt,
    ))
    db.session.commit()

    coin_service.ensure_history(bitcoin, days=30)

    assert len(wywolania) == 0  # API nie wywołane


def test_ensure_history_odpytuje_gdy_baza_pusta(db, bitcoin, monkeypatch):
    """Pusta baza historii → API jest odpytywane."""
    wywolania = []

    def fake_get_history(coingecko_id, days):
        wywolania.append(1)
        return FAKE_HISTORY

    monkeypatch.setattr("app.services.coin_service.get_coin_history", fake_get_history)

    coin_service.ensure_history(bitcoin, days=30)

    assert len(wywolania) == 1


def test_ensure_history_odpytuje_gdy_dane_za_swiezie(db, bitcoin, monkeypatch):
    """Baza ma tylko świeże punkty (z dziś) → API jest odpytywane."""
    wywolania = []

    def fake_get_history(coingecko_id, days):
        wywolania.append(1)
        return FAKE_HISTORY

    monkeypatch.setattr("app.services.coin_service.get_coin_history", fake_get_history)

    # Dodaj tylko świeży punkt (dziś) – niewystarczający dla zakresu 30d
    db.session.add(PriceHistory(
        coin=bitcoin,
        price_usd=68_000.0,
        recorded_at=datetime.now(timezone.utc),
    ))
    db.session.commit()

    coin_service.ensure_history(bitcoin, days=30)

    assert len(wywolania) == 1


# ---------------------------------------------------------------------------
# ensure_history() – zapis punktów
# ---------------------------------------------------------------------------

def test_ensure_history_dodaje_punkty_do_bazy(db, bitcoin, monkeypatch):
    """Pobrane punkty historii są zapisywane w bazie."""
    monkeypatch.setattr(
        "app.services.coin_service.get_coin_history",
        lambda coingecko_id, days: FAKE_HISTORY,
    )

    coin_service.ensure_history(bitcoin, days=30)

    from sqlalchemy import select
    historia = db.session.execute(
        select(PriceHistory).where(PriceHistory.coin_id == bitcoin.id)
    ).scalars().all()

    assert len(historia) == len(FAKE_HISTORY)


def test_ensure_history_blad_api_nie_crashuje(db, bitcoin, monkeypatch):
    """Błąd API w ensure_history nie powoduje wyjątku."""

    def rzuc_blad(coingecko_id, days):
        raise ConnectionError("brak sieci")

    monkeypatch.setattr("app.services.coin_service.get_coin_history", rzuc_blad)

    # Nie powinno rzucić wyjątku
    coin_service.ensure_history(bitcoin, days=30)


# ---------------------------------------------------------------------------
# cleanup_coin_history() – throttling
# ---------------------------------------------------------------------------

def test_cleanup_throttling_blokuje(db, bitcoin, monkeypatch):
    """Drugie wywołanie w ciągu 24h nie wykonuje DELETE."""
    from sqlalchemy import select

    # Dodaj stary punkt do usunięcia
    stary = datetime.now(timezone.utc) - timedelta(days=40)
    db.session.add(PriceHistory(coin=bitcoin, price_usd=50_000.0, recorded_at=stary))
    db.session.commit()

    coin_service.cleanup_coin_history(bitcoin.id, days=30)  # pierwsze – usuwa

    # Dodaj kolejny stary punkt
    db.session.add(PriceHistory(coin=bitcoin, price_usd=49_000.0, recorded_at=stary))
    db.session.commit()

    coin_service.cleanup_coin_history(bitcoin.id, days=30)  # drugie – zablokowane

    # Drugi punkt powinien zostać (throttling zablokował DELETE)
    historia = db.session.execute(
        select(PriceHistory).where(PriceHistory.coin_id == bitcoin.id)
    ).scalars().all()
    assert len(historia) == 1


def test_cleanup_throttling_po_czasie(db, bitcoin):
    """Po upływie _CLEANUP_INTERVAL DELETE jest wykonywany ponownie."""
    from sqlalchemy import select

    stary = datetime.now(timezone.utc) - timedelta(days=40)
    db.session.add(PriceHistory(coin=bitcoin, price_usd=50_000.0, recorded_at=stary))
    db.session.commit()

    # Symuluj że ostatnie czyszczenie było 25 godzin temu (> 24h interwału)
    coin_service._last_cleanup[bitcoin.id] = (
            datetime.now(timezone.utc) - timedelta(hours=25)
    )

    coin_service.cleanup_coin_history(bitcoin.id, days=30)

    historia = db.session.execute(
        select(PriceHistory).where(PriceHistory.coin_id == bitcoin.id)
    ).scalars().all()
    assert len(historia) == 0  # stary punkt usunięty


# ---------------------------------------------------------------------------
# cleanup_coin_history() – logika usuwania
# ---------------------------------------------------------------------------

def test_cleanup_usuwa_stare_punkty(db, bitcoin):
    """Punkty starsze niż N dni zostają usunięte."""
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    stary = now - timedelta(days=40)
    nowy = now - timedelta(days=10)

    db.session.add(PriceHistory(coin=bitcoin, price_usd=50_000.0, recorded_at=stary))
    db.session.add(PriceHistory(coin=bitcoin, price_usd=60_000.0, recorded_at=nowy))
    db.session.commit()

    coin_service.cleanup_coin_history(bitcoin.id, days=30)

    historia = db.session.execute(
        select(PriceHistory).where(PriceHistory.coin_id == bitcoin.id)
    ).scalars().all()

    assert len(historia) == 1
    assert historia[0].price_usd == 60_000.0  # tylko nowy punkt pozostał


def test_cleanup_nie_usuwa_nowych_punktow(db, bitcoin):
    """Punkty w zakresie N dni nie są usuwane."""
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    db.session.add(PriceHistory(coin=bitcoin, price_usd=68_000.0,
                                recorded_at=now - timedelta(days=1)))
    db.session.add(PriceHistory(coin=bitcoin, price_usd=67_000.0,
                                recorded_at=now - timedelta(days=15)))
    db.session.commit()

    coin_service.cleanup_coin_history(bitcoin.id, days=30)

    historia = db.session.execute(
        select(PriceHistory).where(PriceHistory.coin_id == bitcoin.id)
    ).scalars().all()

    assert len(historia) == 2  # oba punkty zachowane


def test_cleanup_aktualizuje_last_cleanup(db, bitcoin):
    """Po cleanup _last_cleanup[coin_id] jest ustawiony."""
    assert coin_service._last_cleanup.get(bitcoin.id) is None

    coin_service.cleanup_coin_history(bitcoin.id, days=30)

    assert coin_service._last_cleanup.get(bitcoin.id) is not None


def test_cleanup_tylko_dla_danej_monety(db, bitcoin):
    """Cleanup usuwa tylko punkty danej monety – nie dotyka innych."""
    from sqlalchemy import select

    # Druga moneta
    inna = Coin(coingecko_id="ethereum", symbol="ETH", name="Ethereum",
                current_price_usd=2_000.0)
    db.session.add(inna)
    db.session.flush()

    now = datetime.now(timezone.utc)
    stary = now - timedelta(days=40)

    db.session.add(PriceHistory(coin=bitcoin, price_usd=50_000.0, recorded_at=stary))
    db.session.add(PriceHistory(coin=inna, price_usd=1_500.0, recorded_at=stary))
    db.session.commit()

    # Czyść tylko bitcoin
    coin_service.cleanup_coin_history(bitcoin.id, days=30)

    # Punkt Ethereum powinien zostać nienaruszony
    historia_eth = db.session.execute(
        select(PriceHistory).where(PriceHistory.coin_id == inna.id)
    ).scalars().all()
    assert len(historia_eth) == 1
