"""
Serwis odpowiedzialny za pobieranie i zarządzanie danymi kryptowalut.

Odpowiedzialności:
    - aktualizacja aktualnych cen z CoinGecko (throttling co _UPDATE_INTERVAL)
    - gwarantowanie historii w bazie przed wyrenderowaniem wykresu
    - czyszczenie starych punktów historii (throttling co 24h per-moneta)

Nie odpowiada za:
    - zapytania SQL (coin_repository, price_history_repository)
    - renderowanie HTML / JSON (coin_routes)
    - obsługę HTTP requestów (coin_routes)

Konwencja commit:
    Serwis jest jedynym miejscem gdzie wywoływany jest db.session.commit().
    Repozytorium używa wyłącznie flush() – staging bez zatwierdzenia.
    Dzięki temu cała operacja (np. upsert monety + dodanie PriceHistory)
    jest atomowa: albo wszystko się zapisuje, albo rollback cofa wszystko.
"""
from datetime import datetime, timezone, timedelta

from app.api_clients import coingecko_client
from app.api_clients.coingecko_client import get_coin_history
from app.extensions import db
from app.models.coin import Coin
from app.repositories import coin_repository, price_history_repository

# ---------------------------------------------------------------------------
# Throttling – stan modułu
# ---------------------------------------------------------------------------

_UPDATE_INTERVAL = timedelta(minutes=5)
_ENSURE_INTERVAL = timedelta(minutes=10)
_CLEANUP_INTERVAL = timedelta(hours=24)

_last_update: datetime | None = None

# Klucz: (coin_id, days) → kiedy ostatnio sprawdzano historię
_ensure_checked: dict[tuple[int, int], datetime] = {}

# Klucz: coin_id → kiedy ostatnio czyszczono historię
_last_cleanup: dict[int, datetime] = {}


# ---------------------------------------------------------------------------
# Publiczne API serwisu
# ---------------------------------------------------------------------------

def update_prices() -> None:
    """
    Pobiera aktualne ceny z CoinGecko i zapisuje do bazy.

    Throttling: odpytuje API max raz na _UPDATE_INTERVAL (5 min).
    Przy każdym udanym pobraniu:
        - upsert monet (create przez repo jeśli nowa, update pól jeśli istnieje)
        - stage_point dla każdej monety (PriceHistory bez commit)
        - jeden commit na końcu dla wszystkich zmian naraz

    Wywoływana przy każdym GET /coins/.
    """
    global _last_update

    now = datetime.now(timezone.utc)
    if _last_update and (now - _last_update) < _UPDATE_INTERVAL:
        return

    try:
        raw_coins = coingecko_client.get_top_coins()
    except Exception:
        return  # błąd sieci – pokazujemy stare dane

    for raw in raw_coins:
        coingecko_id = raw.get("id")
        if not coingecko_id:
            continue

        price = raw.get("current_price")
        if price is None:
            continue

        # Upsert – repo tworzy nową monetę lub zwracamy istniejącą
        coin = coin_repository.find_by_coingecko_id(coingecko_id)
        if coin is None:
            coin = coin_repository.create(coingecko_id)  # flush w repo, commit tu

        # Aktualizacja pól – SQLAlchemy śledzi zmiany automatycznie
        coin.symbol = raw.get("symbol", "").upper()
        coin.name = raw.get("name", coingecko_id)
        coin.current_price_usd = price
        coin.market_cap = raw.get("market_cap")
        coin.price_change_24h = raw.get("price_change_percentage_24h")
        coin.last_updated = now

        # Staging punktu historii – bez commit
        price_history_repository.stage_point(coin, price, now)

    db.session.commit()  # jeden commit dla wszystkich monet i historii
    _last_update = now


def get_all_coins() -> list[Coin]:
    """
    Zwraca wszystkie monety posortowane malejąco po zmianie ceny 24h.

    Returns:
        Lista obiektów Coin – pusta jeśli baza nie ma jeszcze danych.
    """
    return coin_repository.find_all()


def get_coin_by_id(coin_id: int) -> Coin | None:
    """
    Zwraca monetę po jej id w bazie.

    Args:
        coin_id: Klucz główny monety.

    Returns:
        Obiekt Coin lub None jeśli nie istnieje.
    """
    return coin_repository.find_by_id(coin_id)


def ensure_history(coin: Coin, days: int) -> None:
    """
    Gwarantuje że baza ma dane historyczne sięgające (teraz - days) wstecz.

    Throttling: sprawdzenie wykonywane max raz na _ENSURE_INTERVAL (10 min)
    dla każdej pary (coin_id, days). Zapobiega zbędnym SELECT i wywołaniom
    API przy dużym ruchu na tej samej stronie monety.

    Logika:
        1. Czy sprawdzano niedawno? → return (throttling w RAM)
        2. Czy najstarszy punkt w bazie sięga wystarczająco wstecz? → return
        3. Pobierz brakującą historię z CoinGecko (max 1 zapytanie)
        4. stage_bulk – dodaj brakujące punkty bez commit
        5. commit jeśli cokolwiek dodano

    Wywoływana przez coin_routes.history_api() przed zwróceniem danych.

    Args:
        coin: Obiekt Coin dla którego uzupełniamy historię.
        days: Wymagana głębokość historii w dniach.
    """
    now = datetime.now(timezone.utc)
    key = (coin.id, days)
    cutoff = now - timedelta(days=days)

    # Throttling – nie sprawdzaj bazy częściej niż co _ENSURE_INTERVAL
    last_checked = _ensure_checked.get(key)
    if last_checked and (now - last_checked) < _ENSURE_INTERVAL:
        return

    oldest = price_history_repository.find_oldest_by_coin_id(coin.id)

    if oldest is not None:
        oldest_dt = oldest.recorded_at
        if oldest_dt.tzinfo is None:
            oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
        if oldest_dt <= cutoff:
            _ensure_checked[key] = now  # dane wystarczające – zapamiętaj
            return

    # Brakuje danych – pobierz z CoinGecko
    try:
        raw_history = get_coin_history(coin.coingecko_id, days=days)
    except Exception:
        return  # błąd API – pokazujemy co mamy w bazie

    # Jeśli dotarliśmy tutaj early return już nie zadziałał – czyli:
    #   a) oldest is None → baza pusta
    #   b) oldest_dt > cutoff → mamy tylko świeże punkty, brakuje historycznych
    # W OBU przypadkach chcemy dodać CAŁĄ historię z API → cutoff_ts = 0.0
    # Poprzedni kod ustawiał cutoff_ts = oldest_dt.timestamp() gdy oldest_dt > cutoff
    # co powodowało pominięcie CAŁEJ historii (wszystkie punkty API były starsze).
    cutoff_ts = 0.0

    added = price_history_repository.stage_bulk(coin, raw_history, cutoff_ts)

    if added:
        db.session.commit()

    _ensure_checked[key] = now


def cleanup_coin_history(coin_id: int, days: int = 30) -> None:
    """
    Usuwa punkty historii starsze niż N dni dla konkretnej monety.

    Throttling: fizyczne DELETE wykonywane max raz na _CLEANUP_INTERVAL (24h)
    dla każdej monety. Bezpiecznie wywoływać przy każdym GET /coins/<id> –
    bez throttlingu powodowałoby zbędny DELETE przy każdym odświeżeniu.

    Wywoływana przez coin_routes.detail().

    Args:
        coin_id: Klucz główny monety.
        days:    Maksymalny wiek danych w dniach (domyślnie 30).
    """
    now = datetime.now(timezone.utc)
    last = _last_cleanup.get(coin_id)

    if last and (now - last) < _CLEANUP_INTERVAL:
        return  # czyszczono niedawno – pomijamy

    cutoff = now - timedelta(days=days)
    price_history_repository.delete_older_than_for_coin(coin_id, cutoff)
    db.session.commit()

    _last_cleanup[coin_id] = now


