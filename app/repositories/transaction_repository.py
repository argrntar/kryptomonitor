"""
Repozytorium dla tabeli transactions.

Odpowiedzialności:
    - staging nowych transakcji (bez commit – commit w serwisie)
    - pobieranie ostatnich N transakcji dla dashboardu
    - paginacja pełnej historii dla /portfolio/history
    - pobieranie wszystkich transakcji do eksportu CSV
    - zliczanie transakcji użytkownika

Konwencja flush vs commit:
    stage() używa db.session.add() bez flush/commit – nowa transakcja
    dodana do sesji ale nie zatwierdzona. Commit należy do serwisu który
    orkiestruje całą operację (buy = update holding + stage tx = 1 commit).

Używane przez:
    - portfolio_service.py  (_stage_buy, _stage_sell,
                             get_dashboard_data, get_history_page, get_export_data)
"""
from sqlalchemy import select, func

from app.extensions import db
from app.models.transaction import Transaction

DASHBOARD_LIMIT = 10  # ile transakcji na dashboardzie
HISTORY_PER_PAGE = 15  # ile transakcji na stronie historii


def stage(
        user_id: int,
        coin_id: int,
        transaction_type: str,
        amount: float,
        price_usd: float,
        total_usd: float,
) -> Transaction:
    """
    Dodaje nową transakcję do sesji bez commitu.

    Commit należy do serwisu który orkiestruje całą operację –
    buy/sell = update salda + update holdingu + stage transakcji = 1 commit.

    Args:
        user_id:          Klucz główny użytkownika.
        coin_id:          Klucz główny monety.
        transaction_type: "buy" lub "sell".
        amount:           Ilość kryptowaluty.
        price_usd:        Cena jednostkowa w USD.
        total_usd:        Wartość całkowita (amount * price_usd).

    Returns:
        Nowy obiekt Transaction dodany do sesji – niezatwierdzony.
    """
    tx = Transaction(
        user_id=user_id,
        coin_id=coin_id,
        transaction_type=transaction_type,
        amount=amount,
        price_usd=price_usd,
        total_usd=total_usd,
    )
    db.session.add(tx)
    return tx


def find_recent_by_user(user_id: int) -> list[Transaction]:
    """
    Zwraca ostatnie N transakcji użytkownika – dla dashboardu.

    Args:
        user_id: Klucz główny użytkownika.

    Returns:
        Lista ostatnich DASHBOARD_LIMIT transakcji posortowanych malejąco.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(DASHBOARD_LIMIT)
    )
    return db.session.execute(stmt).scalars().all()


def find_by_user_paginated(user_id: int, page: int):
    """
    Zwraca stronę historii transakcji użytkownika.

    Używa db.paginate() – oficjalne API Flask-SQLAlchemy 3.x dla paginacji
    z select(). Poprzednia wersja używała .scalars().paginate() które
    nie istnieje w SQLAlchemy 2.0 (ScalarResult nie ma metody paginate).

    Zwraca obiekt Pagination z atrybutami:
        items     – lista transakcji na bieżącej stronie
        pages     – łączna liczba stron
        has_prev  – czy jest poprzednia strona
        has_next  – czy jest następna strona
        prev_num  – numer poprzedniej strony
        next_num  – numer następnej strony

    Args:
        user_id: Klucz główny użytkownika.
        page:    Numer strony (od 1).

    Returns:
        Obiekt flask_sqlalchemy.Pagination.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
    )
    return db.paginate(stmt, page=page, per_page=HISTORY_PER_PAGE, error_out=False)


def find_all_by_user(user_id: int) -> list[Transaction]:
    """
    Zwraca wszystkie transakcje użytkownika – do eksportu CSV.

    Args:
        user_id: Klucz główny użytkownika.

    Returns:
        Lista wszystkich transakcji posortowanych malejąco po dacie.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
    )
    return db.session.execute(stmt).scalars().all()


def count_by_user(user_id: int) -> int:
    """
    Zwraca całkowitą liczbę transakcji użytkownika.

    Args:
        user_id: Klucz główny użytkownika.

    Returns:
        Liczba transakcji.
    """
    stmt = select(func.count()).where(Transaction.user_id == user_id)
    return db.session.execute(stmt).scalar_one()
