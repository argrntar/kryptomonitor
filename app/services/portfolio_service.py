"""
Serwis logiki biznesowej dla operacji portfelowych.

Odpowiedzialności:
    - walidacja i wykonanie operacji kupna/sprzedaży
    - obliczenia P&L (zysk/strata) dla pozycji i całego portfela
    - agregacja danych dla widoków (dashboard, historia, eksport)
    - obliczanie minimalnej ilości sprzedaży (dla trade_routes)

Nie odpowiada za:
    - zapytania SQL – portfolio_repository, transaction_repository, coin_repository
    - renderowanie HTML/CSV – portfolio_routes, trade_routes
    - obsługę HTTP – portfolio_routes, trade_routes

Konwencja prywatne _stage vs publiczne buy/sell:
    _stage_buy() i _stage_sell() – staging bez commit, wywoływane wewnętrznie.
    buy() i sell() – walidacja + staging + commit (operacje standalone).
    close_all() – _stage_sell() wielokrotnie + JEDEN commit dla wszystkich.
    Dzięki temu close_all zapisuje N sprzedaży w jednej atomowej transakcji.

Obliczenia finansowe:
    Wszystkie obliczenia używają decimal.Decimal zamiast float.
    Float nie może dokładnie reprezentować wielu wartości dziesiętnych:
        0.1 + 0.2 = 0.30000000000000004  (float)
        Decimal("0.1") + Decimal("0.2") = Decimal("0.3")  (Decimal)
    Decimal to standard w aplikacjach finansowych.
    Dokumentacja: https://docs.python.org/3/library/decimal.html

    Uwaga: coin.current_price_usd pozostaje float (dane z zewnętrznego API,
    tylko wyświetlane). Wszędzie gdzie cena wchodzi w obliczenia finansowe
    jest konwertowana przez _to_decimal().
"""
from decimal import Decimal, ROUND_UP, ROUND_DOWN
from datetime import datetime, timezone

from app.extensions import db
from app.models.coin import Coin
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction
from app.models.user import User
from app.repositories import portfolio_repository, coin_repository
from app.repositories import transaction_repository
from app.repositories.transaction_repository import DASHBOARD_LIMIT
from app.exceptions import InsufficientFundsError, InsufficientCoinError

MIN_TRANSACTION_USD = Decimal("0.01")

AMOUNT_PRECISION = Decimal("0.0001")
BALANCE_PRECISION = Decimal("0.01")
PRICE_PRECISION = Decimal("0.00000001")
MIN_DUST = Decimal("0.0001")


# ---------------------------------------------------------------------------
# Helpery prywatne – konwersja i zaokrąglanie
# ---------------------------------------------------------------------------

def _to_decimal(value) -> Decimal:
    """
    Konwertuje float, int lub string na Decimal.

    Używa str() jako pośrednika – bezpośrednia konwersja float → Decimal
    przenosi błąd reprezentacji binarnej:
        Decimal(0.1)    = Decimal("0.1000000000000000055511...")  (błąd)
        Decimal("0.1")  = Decimal("0.1")                         (poprawnie)
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_amount(value: Decimal) -> Decimal:
    """Zaokrągla ilość kryptowaluty do 4 miejsc po przecinku (w dół)."""
    return value.quantize(AMOUNT_PRECISION, rounding=ROUND_DOWN)


def _round_balance(value: Decimal) -> Decimal:
    """Zaokrągla saldo USD do 2 miejsc po przecinku (w dół)."""
    return value.quantize(BALANCE_PRECISION, rounding=ROUND_DOWN)


# ---------------------------------------------------------------------------
# Helpery prywatne – staging operacji (bez commit)
# ---------------------------------------------------------------------------

def _stage_buy(
        user: User,
        coin: Coin,
        amount: Decimal,
        price: Decimal,
        total_cost: Decimal,
) -> Transaction:
    """
    Wykonuje kupno bez commitu – staging wszystkich zmian w sesji.

    Woła portfolio_repository.create() jeśli user kupuje monetę po raz pierwszy.
    Aktualizuje pola holdingu (SQLAlchemy śledzi zmiany automatycznie).
    Woła transaction_repository.stage() zamiast db.session.add(Transaction).

    Commit należy do wywołującego (buy() lub close_all()).
    """
    user.balance_usd = _round_balance(_to_decimal(user.balance_usd) - total_cost)

    holding = portfolio_repository.find_by_user_and_coin(user.id, coin.id)
    if holding is None:
        holding = portfolio_repository.create(user.id, coin.id)

    old_amount = _round_amount(_to_decimal(holding.amount))
    old_price = _to_decimal(holding.avg_buy_price)
    new_total = old_amount + amount
    new_avg = (old_amount * old_price + amount * price) / new_total

    holding.avg_buy_price = new_avg.quantize(PRICE_PRECISION, rounding=ROUND_DOWN)
    holding.amount = new_total
    holding.updated_at = datetime.now(timezone.utc)

    # Kolumny transaction są Numeric – przekazujemy Decimal bezpośrednio
    return transaction_repository.stage(
        user_id=user.id,
        coin_id=coin.id,
        transaction_type="buy",
        amount=amount,
        price_usd=price,
        total_usd=total_cost,
    )


def _stage_sell(
        user: User,
        holding: Portfolio,
        amount: Decimal,
        price: Decimal,
        total_value: Decimal,
) -> Transaction:
    """
    Wykonuje sprzedaż bez commitu – staging wszystkich zmian w sesji.

    Aktualizuje saldo i holding (SQLAlchemy śledzi automatycznie).
    Resztki poniżej MIN_DUST są zerowane.

    Commit należy do wywołującego (sell() lub close_all()).
    """
    user.balance_usd = _round_balance(_to_decimal(user.balance_usd) + total_value)

    remaining = _round_amount(_to_decimal(holding.amount)) - amount
    holding.amount = Decimal("0") if remaining < MIN_DUST else remaining
    holding.updated_at = datetime.now(timezone.utc)

    # Kolumny transaction są Numeric – przekazujemy Decimal bezpośrednio
    return transaction_repository.stage(
        user_id=user.id,
        coin_id=holding.coin_id,
        transaction_type="sell",
        amount=amount,
        price_usd=price,
        total_usd=total_value,
    )


# ---------------------------------------------------------------------------
# Publiczne operacje – walidacja + staging + commit
# ---------------------------------------------------------------------------

def buy(user: User, coin: Coin, amount) -> Transaction:
    """
    Kupuje amount jednostek coin dla user.

    Walidacja:
        1. Minimalna wartość transakcji ($0.01)
        2. Wystarczające saldo USD

    Returns:
        Zatwierdzony obiekt Transaction.

    Raises:
        InsufficientFundsError: Wartość < $0.01 lub niewystarczające saldo.
    """
    price = _to_decimal(coin.current_price_usd)
    amount = _round_amount(_to_decimal(amount))
    total_cost = price * amount

    if total_cost < MIN_TRANSACTION_USD:
        min_amount = (MIN_TRANSACTION_USD / price).quantize(
            AMOUNT_PRECISION, rounding=ROUND_UP
        )
        raise InsufficientFundsError(
            f"Minimalna wartość transakcji to ${MIN_TRANSACTION_USD}. "
            f"Przy cenie ${price:,.4f} minimalna ilość to {min_amount} {coin.symbol}."
        )

    if _to_decimal(user.balance_usd) < total_cost:
        raise InsufficientFundsError(
            f"Potrzebujesz ${total_cost:,.2f}, masz ${user.balance_usd:,.2f}."
        )

    tx = _stage_buy(user, coin, amount, price, total_cost)
    db.session.commit()
    return tx


def sell(user: User, coin: Coin, amount) -> Transaction:
    """
    Sprzedaje amount jednostek coin dla user.

    Zaokrągla holding_amount i amount do 4 miejsc przed porównaniem –
    eliminuje błędy float np. 0.009999... zamiast 0.01.

    Returns:
        Zatwierdzony obiekt Transaction.

    Raises:
        InsufficientCoinError: Brak kryptowaluty lub wartość < $0.01.
    """
    holding = portfolio_repository.find_by_user_and_coin(user.id, coin.id)
    amount = _round_amount(_to_decimal(amount))
    holding_amount = _round_amount(_to_decimal(holding.amount)) if holding else Decimal("0")

    if holding is None or holding_amount < amount:
        raise InsufficientCoinError(
            f"Chcesz sprzedać {amount:.4f}, masz {holding_amount:.4f} {coin.symbol}."
        )

    price = _to_decimal(coin.current_price_usd)
    total_value = price * amount

    is_full_sell = amount >= holding_amount
    if not is_full_sell and total_value < MIN_TRANSACTION_USD:
        min_amount = (MIN_TRANSACTION_USD / price).quantize(
            AMOUNT_PRECISION, rounding=ROUND_UP
        )
        if holding_amount < min_amount:
            raise InsufficientCoinError(
                f"Wartość transakcji za niska. "
                f"Wpisz {holding_amount} {coin.symbol} aby sprzedać całość."
            )
        raise InsufficientCoinError(
            f"Minimalna wartość transakcji to ${MIN_TRANSACTION_USD}. "
            f"Przy cenie ${price:,.4f} minimalna ilość to {min_amount} {coin.symbol}."
        )

    tx = _stage_sell(user, holding, amount, price, total_value)
    db.session.commit()
    return tx


def close_all(user: User) -> tuple[int, int]:
    """
    Sprzedaje wszystkie posiadane kryptowaluty po aktualnych cenach.

    Używa _stage_sell() wielokrotnie – każda pozycja stagowana bez commitu.
    JEDEN commit na końcu zatwierdza wszystkie sprzedaże atomowo.

    Returns:
        Tuple (sold, skipped) – ile pozycji sprzedano i pominięto.
    """
    holdings = portfolio_repository.find_by_user(user.id)
    sold = 0
    skipped = 0

    for holding in holdings:
        if _to_decimal(holding.amount) <= Decimal("0"):
            continue

        coin = coin_repository.find_by_id(holding.coin_id)
        if coin is None or coin.current_price_usd is None:
            skipped += 1
            continue

        try:
            amount = _round_amount(_to_decimal(holding.amount))
            price = _to_decimal(coin.current_price_usd)
            total_value = price * amount
            _stage_sell(user, holding, amount, price, total_value)
            sold += 1
        except Exception:
            skipped += 1

    if sold > 0:
        db.session.commit()

    return sold, skipped


# ---------------------------------------------------------------------------
# Obliczenia P&L
# ---------------------------------------------------------------------------

def build_positions(
        holdings: list[Portfolio],
        coins_map: dict[int, Coin],
) -> tuple[list[dict], Decimal, Decimal]:
    """
    Buduje listę pozycji z P&L na podstawie holdings i aktualnych cen.

    Należy do serwisu – to logika biznesowa (obliczenia finansowe).
    Routes delegują tu obliczenia i przekazują wynik do szablonu.

    coin.current_price_usd jest float (dane z API) – konwertowany przez
    _to_decimal() przed każdym obliczeniem finansowym.

    Returns:
        Tuple (positions, total_value, total_cost) – wartości jako Decimal.
    """
    positions = []
    total_value = Decimal("0")
    total_cost = Decimal("0")

    for holding in holdings:
        if _to_decimal(holding.amount) <= Decimal("0"):
            continue
        coin = coins_map.get(holding.coin_id)
        if coin is None:
            continue

        # coin.current_price_usd to float – konwertujemy przed obliczeniami
        if coin.current_price_usd is not None:
            current_price = _to_decimal(coin.current_price_usd)
        else:
            current_price = _to_decimal(holding.avg_buy_price)

        amount = _to_decimal(holding.amount)
        avg_buy = _to_decimal(holding.avg_buy_price)

        current_value = amount * current_price
        cost_basis = amount * avg_buy
        pnl_usd = current_value - cost_basis
        pnl_pct = (pnl_usd / cost_basis * 100) if cost_basis > Decimal("0") else Decimal("0")

        positions.append({
            "holding": holding,
            "coin": coin,
            "current_price": current_price,
            "current_value": current_value,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "is_positive": pnl_usd >= Decimal("0"),
        })

        total_value += current_value
        total_cost += cost_basis

    return positions, total_value, total_cost


def get_min_sell_amount(coin: Coin) -> Decimal | None:
    """
    Oblicza minimalną ilość kryptowaluty możliwą do sprzedaży.

    Minimalna wartość transakcji to $0.01. Dla droższych monet
    minimalna ilość może być większa niż AMOUNT_PRECISION (0.0001).

    Należy do serwisu – to obliczenie biznesowe (MIN_TRANSACTION_USD),
    nie logika prezentacji. trade_routes deleguje tu obliczenie
    zamiast robić Decimal math bezpośrednio w route.

    Args:
        coin: Moneta z aktualną ceną.

    Returns:
        Minimalna ilość jako Decimal lub None jeśli brak ceny
        albo minimalna ilość = AMOUNT_PRECISION (brak specjalnego info).
    """
    if not coin.current_price_usd:
        return None
    price = _to_decimal(coin.current_price_usd)
    min_amount = (MIN_TRANSACTION_USD / price).quantize(
        AMOUNT_PRECISION, rounding=ROUND_UP
    )
    return min_amount if min_amount > AMOUNT_PRECISION else None


# ---------------------------------------------------------------------------
# Agregacja danych dla widoków
# ---------------------------------------------------------------------------

def get_dashboard_data(user_id: int) -> dict:
    """
    Agreguje wszystkie dane potrzebne do wyrenderowania dashboardu portfela.

    Args:
        user_id: Klucz główny zalogowanego użytkownika.

    Returns:
        Słownik z kluczami: positions, summary, transactions,
        coins_map, has_more_history, total_tx_count.
    """
    holdings = portfolio_repository.find_by_user(user_id)
    coin_ids = [h.coin_id for h in holdings]
    coins = coin_repository.find_by_ids(coin_ids)
    coins_map = {c.id: c for c in coins}

    positions, total_value, total_cost = build_positions(holdings, coins_map)

    total_pnl_usd = total_value - total_cost
    total_pnl_pct = (total_pnl_usd / total_cost * 100) if total_cost > Decimal("0") else Decimal("0")

    summary = {
        "total_value": total_value,
        "total_pnl_usd": total_pnl_usd,
        "total_pnl_pct": total_pnl_pct,
        "is_positive": total_pnl_usd >= Decimal("0"),
    }

    transactions = transaction_repository.find_recent_by_user(user_id)
    total_tx_count = transaction_repository.count_by_user(user_id)

    tx_coin_ids = list({tx.coin_id for tx in transactions} - set(coin_ids))
    tx_coins = coin_repository.find_by_ids(tx_coin_ids)
    coins_map_full = {**coins_map, **{c.id: c for c in tx_coins}}

    return {
        "positions": positions,
        "summary": summary,
        "transactions": transactions,
        "coins_map": coins_map_full,
        "has_more_history": total_tx_count > DASHBOARD_LIMIT,
        "total_tx_count": total_tx_count,
    }


def get_history_page(user_id: int, page: int) -> dict:
    """
    Pobiera jedną stronę historii transakcji z paginacją.

    Returns:
        Słownik z kluczami: pagination, transactions, coins_map, total_count.
    """
    pagination = transaction_repository.find_by_user_paginated(user_id, page=page)
    coin_ids = list({tx.coin_id for tx in pagination.items})
    coins = coin_repository.find_by_ids(coin_ids)
    coins_map = {c.id: c for c in coins}

    return {
        "pagination": pagination,
        "transactions": pagination.items,
        "coins_map": coins_map,
        "total_count": transaction_repository.count_by_user(user_id),
    }


def get_export_data(user_id: int) -> tuple[list[Transaction], dict[int, Coin]]:
    """
    Pobiera wszystkie transakcje z mapą monet – do eksportu CSV.

    Formatowanie CSV należy do routes (warstwa prezentacji).
    Serwis dostarcza tylko surowe dane.

    Returns:
        Tuple (transactions, coins_map).
    """
    transactions = transaction_repository.find_all_by_user(user_id)
    coin_ids = list({tx.coin_id for tx in transactions})
    coins = coin_repository.find_by_ids(coin_ids)
    coins_map = {c.id: c for c in coins}
    return transactions, coins_map


def get_nav_pnl(user: User) -> dict | None:
    """
    Oblicza P&L dla paska nawigacji.

    Lekka wersja build_positions() – tylko suma wartości i kosztów.
    Wywoływana przez context processor przy każdym requeście zalogowanego
    użytkownika. Zwraca None jeśli user nie ma żadnych pozycji.

    Returns:
        Słownik z kluczami pnl_usd, pnl_pct, is_positive lub None.
    """
    holdings = portfolio_repository.find_by_user(user.id)
    active = [h for h in holdings if _to_decimal(h.amount) > Decimal("0")]
    if not active:
        return None

    coin_ids = [h.coin_id for h in active]
    coins_map = {c.id: c for c in coin_repository.find_by_ids(coin_ids)}

    total_value = Decimal("0")
    total_cost = Decimal("0")

    for holding in active:
        coin = coins_map.get(holding.coin_id)
        if coin is None:
            continue
        price = _to_decimal(coin.current_price_usd) if coin.current_price_usd is not None else _to_decimal(holding.avg_buy_price)
        amount = _to_decimal(holding.amount)
        total_value += amount * price
        total_cost += amount * _to_decimal(holding.avg_buy_price)

    pnl_usd = total_value - total_cost
    pnl_pct = (pnl_usd / total_cost * 100) if total_cost > Decimal("0") else Decimal("0")

    return {
        "pnl_usd": pnl_usd,
        "pnl_pct": pnl_pct,
        "is_positive": pnl_usd >= Decimal("0"),
    }