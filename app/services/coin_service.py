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

Throttling update_prices():
    Poprzednia implementacja używała zmiennej modułu _last_update (datetime).
    Problem: gunicorn uruchamia wiele workerów – każdy ma własną pamięć
    i własną kopię _last_update. Przy 4 workerach CoinGecko było odpytywane
    4x częściej niż zakładano, co mogło przekroczyć limit API.

    Obecna implementacja sprawdza last_updated bezpośrednio z bazy przez
    coin_repository.find_most_recently_updated(). Wszystkie workery czytają
    ten sam rekord – throttling działa globalnie dla całego procesu gunicorn.
"""
from datetime import datetime, timezone, timedelta

from app.api_clients import coingecko_client
from app.api_clients.coingecko_client import get_coin_history
from app.extensions import db
from app.models.coin import Coin
from app.repositories import coin_repository, price_history_repository

# ---------------------------------------------------------------------------
# Throttling – interwały
# ---------------------------------------------------------------------------

_UPDATE_INTERVAL = timedelta(minutes=5)
_ENSURE_INTERVAL = timedelta(minutes=10)
_CLEANUP_INTERVAL = timedelta(hours=24)

# Klucz: (coin_id, days) → kiedy ostatnio sprawdzano historię
# Uwaga: te słowniki są per-worker (pamięć procesu). Przy wielu workerach
# mogą spowodować dodatkowe zapytania do CoinGecko o historię lub dodatkowy
# DELETE przy czyszczeniu – konsekwencje niegroźne dla działania aplikacji.
_ensure_checked: dict[tuple[int, int], datetime] = {}
_last_cleanup: dict[int, datetime] = {}


# ---------------------------------------------------------------------------
# Publiczne API serwisu
# ---------------------------------------------------------------------------

def update_prices() -> None:
    """
    Pobiera aktualne ceny z CoinGecko i zapisuje do bazy.

    Throttling przez bazę danych: odpytuje API max raz na _UPDATE_INTERVAL
    (5 min). Sprawdza last_updated ostatnio zaktualizowanej monety zamiast
    zmiennej modułu – działa poprawnie z wieloma workerami gunicorn.

    Przy każdym udanym pobraniu:
        - upsert monet (create przez repo jeśli nowa, update pól jeśli istnieje)
        - stage_point dla każdej monety (PriceHistory bez commit)
        - jeden commit na końcu dla wszystkich zmian naraz

    Wywoływana przy każdym GET /coins/.
    """
    now = datetime.now(timezone.utc)

    # Throttling przez bazę – działa z wieloma workerami gunicorn.
    # Każdy worker czyta ten sam rekord zamiast własnej zmiennej w pamięci.
    newest_coin = coin_repository.find_most_recently_updated()
    if newest_coin and newest_coin.last_updated:
        last = newest_coin.last_updated
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last) < _UPDATE_INTERVAL:
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
            coin = coin_repository.create(coingecko_id)

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
            _ensure_checked[key] = now
            return

    try:
        raw_history = get_coin_history(coin.coingecko_id, days=days)
    except Exception:
        return  # błąd API – pokazujemy co mamy w bazie

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
        return

    cutoff = now - timedelta(days=days)
    price_history_repository.delete_older_than_for_coin(coin_id, cutoff)
    db.session.commit()

    _last_cleanup[coin_id] = now
