"""
Repozytorium odpowiedzialne za dostęp do danych monet w bazie.

Odpowiedzialności:
    - pobieranie monet według różnych kryteriów (id, coingecko_id, lista id)
    - tworzenie nowych monet (INSERT z flush – commit należy do serwisu)
    - brak logiki biznesowej – tylko zapytania do bazy

Używane przez:
    - coin_service.py        (update_prices, get_all_coins, get_coin_by_id,
                              ensure_history, cleanup_coin_history)
    - portfolio_routes.py    (find_by_ids – dashboard, historia, eksport CSV)
    - portfolio_service.py   (find_by_id – close_all)

Konwencja flush vs commit:
    Metody zapisu używają db.session.flush() – wysyłają SQL do bazy
    ale NIE zatwierdzają transakcji. Commit należy do serwisu który
    orkiestruje całą operację i może wycofać wiele zmian naraz.
"""
from sqlalchemy import select

from app.extensions import db
from app.models.coin import Coin


def find_all() -> list[Coin]:
    """
    Zwraca wszystkie monety posortowane malejąco po zmianie ceny 24h.

    Monety bez danych price_change_24h (NULL) trafiają na koniec listy
    dzięki nullslast().

    Returns:
        Lista obiektów Coin posortowana malejąco po price_change_24h.
    """
    stmt = select(Coin).order_by(Coin.price_change_24h.desc().nullslast())
    return db.session.execute(stmt).scalars().all()


def find_by_id(coin_id: int) -> Coin | None:
    """
    Zwraca monetę po kluczu głównym.

    Używa db.session.get() zamiast query.get() – korzysta z identity map
    sesji SQLAlchemy, co oznacza brak dodatkowego zapytania do bazy jeśli
    obiekt jest już w pamięci sesji.

    Args:
        coin_id: Klucz główny monety (kolumna id).

    Returns:
        Obiekt Coin lub None jeśli nie istnieje.
    """
    return db.session.get(Coin, coin_id)


def find_by_coingecko_id(coingecko_id: str) -> Coin | None:
    """
    Zwraca monetę po jej identyfikatorze z CoinGecko.

    Używane przy upsert w coin_service.update_prices() – sprawdza czy moneta
    o danym coingecko_id już istnieje w bazie przed ewentualnym utworzeniem.

    Args:
        coingecko_id: Identyfikator monety w API CoinGecko, np. "bitcoin".

    Returns:
        Obiekt Coin lub None jeśli nie istnieje.
    """
    stmt = select(Coin).filter_by(coingecko_id=coingecko_id)
    return db.session.execute(stmt).scalar_one_or_none()


def find_by_ids(coin_ids: list[int]) -> list[Coin]:
    """
    Zwraca listę monet dla podanych kluczy głównych.

    Używana gdy potrzebujesz pobrać wiele monet jednym zapytaniem zamiast
    N osobnych find_by_id(). Używana w portfolio_routes (dashboard, historia,
    eksport CSV) gdzie użytkownik posiada wiele monet jednocześnie.

    Args:
        coin_ids: Lista kluczy głównych monet.

    Returns:
        Lista obiektów Coin – kolejność nie jest gwarantowana.
        Zwraca pustą listę jeśli coin_ids jest puste.
    """
    if not coin_ids:
        return []
    stmt = select(Coin).where(Coin.id.in_(coin_ids))
    return db.session.execute(stmt).scalars().all()


def find_most_recently_updated() -> Coin | None:
    """
    Zwraca monetę z najnowszym last_updated.

    Używana przez coin_service.update_prices() do throttlingu opartego
    na bazie danych zamiast zmiennej modułu w pamięci procesu. Dzięki temu
    throttling działa poprawnie z wieloma workerami gunicorn – wszystkie
    workery czytają ten sam rekord zamiast własnych kopii zmiennej _last_update.

    Returns:
        Obiekt Coin z najnowszym last_updated lub None jeśli baza pusta.
    """
    stmt = select(Coin).order_by(Coin.last_updated.desc().nullslast()).limit(1)
    return db.session.execute(stmt).scalar_one_or_none()


def create(coingecko_id: str) -> Coin:
    """
    Tworzy nową monetę i dodaje ją do sesji bez flush/commit.

    NIE używa flush() – Coin ma pola NOT NULL (symbol, name) które są
    ustawiane przez serwis PO wywołaniu create(). Flush przed ustawieniem
    tych pól spowodowałby IntegrityError (NOT NULL constraint failed).

    SQLAlchemy sam ustali kolejność insertów przy commit() – Coin wstawi
    przed PriceHistory dzięki śledzeniu relacji w unit of work.

    Commit należy do serwisu (coin_service.update_prices).

    Args:
        coingecko_id: Identyfikator monety w API CoinGecko, np. "bitcoin".

    Returns:
        Nowy obiekt Coin – niezatwierdzony, pola symbol/name do ustawienia.
    """
    coin = Coin(coingecko_id=coingecko_id)
    db.session.add(coin)
    return coin
