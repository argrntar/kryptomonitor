"""
Repozytorium dla tabeli portfolio (pozycje użytkowników).

Odpowiedzialności:
    - pobieranie pozycji dla konkretnego użytkownika
    - pobieranie konkretnej pozycji (user + coin)
    - tworzenie nowej pozycji (INSERT z flush – commit należy do serwisu)

Nie odpowiada za:
    - logikę biznesową (obliczenia, walidacja) – portfolio_service
    - commit transakcji – portfolio_service

Konwencja flush vs commit:
    create() używa flush() – nowy obiekt dostaje id ale transakcja
    NIE jest zatwierdzona. Commit należy do serwisu który orkiestruje
    całą operację (np. create holding + stage transaction = jeden commit).

Używane przez:
    - portfolio_service.py  (buy, sell, close_all, get_dashboard_data)
    - trade_routes.py       (trade_form – czy user posiada monetę)
    - coin_routes.py        (detail – czy user posiada monetę)
"""
from sqlalchemy import select
from decimal import Decimal
from app.extensions import db
from app.models.portfolio import Portfolio


def find_by_user(user_id: int) -> list[Portfolio]:
    """
    Zwraca wszystkie pozycje portfelowe użytkownika.

    Args:
        user_id: Klucz główny użytkownika.

    Returns:
        Lista obiektów Portfolio – pusta jeśli użytkownik nie ma pozycji.
    """
    stmt = select(Portfolio).filter_by(user_id=user_id)
    return db.session.execute(stmt).scalars().all()


def find_by_user_and_coin(user_id: int, coin_id: int) -> Portfolio | None:
    """
    Zwraca pozycję użytkownika dla konkretnej monety.

    Używana przy kupnie/sprzedaży (upsert w portfolio_service)
    oraz przy wyświetlaniu strony szczegółowej monety (czy user ją posiada).

    Args:
        user_id: Klucz główny użytkownika.
        coin_id: Klucz główny monety.

    Returns:
        Obiekt Portfolio lub None jeśli użytkownik nie posiada tej monety.
    """
    stmt = select(Portfolio).filter_by(user_id=user_id, coin_id=coin_id)
    return db.session.execute(stmt).scalar_one_or_none()


def create(user_id: int, coin_id: int) -> Portfolio:
    """
    Tworzy nową pozycję portfelową z zerową ilością i zwraca ją z id.

    Używa flush() zamiast commit() – obiekt dostaje id z bazy i może
    być użyty w tej samej sesji (np. do aktualizacji pól w serwisie),
    ale transakcja NIE jest zatwierdzona. Commit należy do serwisu.

    Wywoływana przez portfolio_service.buy() gdy user kupuje monetę
    po raz pierwszy i nie ma jeszcze pozycji w portfelu.

    Args:
        user_id: Klucz główny użytkownika.
        coin_id: Klucz główny monety.

    Returns:
        Nowy obiekt Portfolio z id – niezatwierdzony w bazie.
    """
    holding = Portfolio(
        user_id=user_id,
        coin_id=coin_id,
        amount=Decimal("0"),
        avg_buy_price=Decimal("0"),
    )
    db.session.add(holding)
    db.session.flush()  # id dostępne, commit w serwisie
    return holding
