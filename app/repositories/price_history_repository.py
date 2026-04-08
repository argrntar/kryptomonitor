"""
Repozytorium dla tabeli price_history.

Odpowiedzialności:
    - odczyt historii dla wykresu (zakres czasowy, najstarszy punkt)
    - staging nowych punktów cenowych (bez commit – commit w serwisie)
    - usuwanie starych punktów (bez commit – commit w serwisie)

Konwencja flush vs commit:
    Metody zapisu/usuwania NIE commitują – commit należy do serwisu
    który orkiestruje całą operację. Dzięki temu np. update_prices()
    może zapisać wiele monet i ich historię w jednej atomowej transakcji.

Używane przez:
    - coin_service.py   (update_prices, ensure_history, cleanup_coin_history)
    - coin_routes.py    (history_api → find_since)
"""
from datetime import datetime, timezone

from sqlalchemy import select, delete

from app.extensions import db
from app.models.coin import Coin
from app.models.price_history import PriceHistory


def find_since(coin_id: int, since: datetime) -> list[PriceHistory]:
    """
    Zwraca punkty historii od podanej daty do teraz.

    Używane przez history_api() do filtrowania po zakresie czasowym.

    Args:
        coin_id: Klucz główny monety.
        since:   Data początkowa przedziału (włącznie).

    Returns:
        Lista PriceHistory posortowana rosnąco po recorded_at.
    """
    stmt = (
        select(PriceHistory)
        .where(PriceHistory.coin_id == coin_id)
        .where(PriceHistory.recorded_at >= since)
        .order_by(PriceHistory.recorded_at.asc())
    )
    return db.session.execute(stmt).scalars().all()


def find_oldest_by_coin_id(coin_id: int) -> PriceHistory | None:
    """
    Zwraca najstarszy punkt historii dla danej monety.

    Używane przez ensure_history() do sprawdzenia czy baza ma dane
    sięgające wystarczająco daleko wstecz.

    Args:
        coin_id: Klucz główny monety.

    Returns:
        Najstarszy obiekt PriceHistory lub None jeśli brak historii.
    """
    stmt = (
        select(PriceHistory)
        .where(PriceHistory.coin_id == coin_id)
        .order_by(PriceHistory.recorded_at.asc())
        .limit(1)
    )
    return db.session.execute(stmt).scalar_one_or_none()


def stage_point(coin: Coin, price_usd: float, recorded_at: datetime) -> None:
    """
    Dodaje pojedynczy punkt historii ceny do sesji bez commitu.

    Używana w update_prices() – wiele punktów dodawanych w pętli,
    jeden commit na końcu zatwierdza je wszystkie naraz.

    Args:
        coin:        Obiekt Coin do którego należy punkt.
        price_usd:   Cena w USD.
        recorded_at: Czas zapisu punktu (datetime UTC).
    """
    db.session.add(PriceHistory(
        coin=coin,
        price_usd=price_usd,
        recorded_at=recorded_at,
    ))


def stage_bulk(coin: Coin, points: list[list[float]], cutoff_ts: float) -> int:
    """
    Dodaje wiele punktów historii do sesji bez commitu.

    Używana w ensure_history() po pobraniu historii z CoinGecko.
    Filtruje punkty starsze niż cutoff_ts i dodaje tylko brakujące.

    cutoff_ts = 0.0 oznacza dodaj wszystkie punkty z API
    (gdy baza jest pusta lub ma tylko świeże punkty z update_prices).

    Args:
        coin:      Obiekt Coin do którego należą punkty.
        points:    Lista list [timestamp_ms, price_usd] z CoinGecko API.
        cutoff_ts: Timestamp w ms – pomijaj punkty starsze lub równe.
                   Przekaż 0.0 żeby dodać wszystkie punkty.

    Returns:
        Liczba dodanych punktów.
    """
    added = 0
    for timestamp_ms, price in points:
        if timestamp_ms <= cutoff_ts:
            continue
        db.session.add(PriceHistory(
            coin=coin,
            price_usd=price,
            recorded_at=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
        ))
        added += 1
    return added


def delete_older_than_for_coin(coin_id: int, cutoff: datetime) -> None:
    """
    Usuwa punkty historii starsze niż cutoff dla konkretnej monety.

    Używana w cleanup_coin_history() – nie commituje,
    commit należy do coin_service.

    Args:
        coin_id: Klucz główny monety.
        cutoff:  Punkty starsze niż ta data zostaną usunięte.
    """
    stmt = (
        delete(PriceHistory)
        .where(PriceHistory.coin_id == coin_id)
        .where(PriceHistory.recorded_at < cutoff)
    )
    db.session.execute(stmt)
