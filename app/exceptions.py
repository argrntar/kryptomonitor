"""
Wyjątki domenowe aplikacji.

Własne wyjątki zamiast ogólnych Exception pozwalają:
    - łapać konkretne błędy w routes (except InsufficientFundsError)
    - nie łapać przypadkowo innych błędów programistycznych
    - czytelnie komunikować co poszło nie tak

Używane aktualnie:
    InsufficientFundsError  – portfolio_service.buy(), trade_routes
    InsufficientCoinError   – portfolio_service.sell(), trade_routes
    ExternalAPIError        – coingecko_client, coin_service

Zdefiniowane ale nieużywane (zarezerwowane na przyszłość):
    CoinNotFoundError   – potencjalnie przydatne gdy API zwróci nieznaną monetę
    UserNotFoundError   – potencjalnie przydatne w przyszłym admin panel
"""


class InsufficientFundsError(Exception):
    """Użytkownik nie ma wystarczającego salda USD do wykonania transakcji."""


class InsufficientCoinError(Exception):
    """Użytkownik nie ma wystarczającej ilości kryptowaluty do sprzedaży."""


class ExternalAPIError(Exception):
    """Błąd komunikacji z zewnętrznym API (np. CoinGecko niedostępny lub 429)."""


class CoinNotFoundError(Exception):
    """Kryptowaluta nie istnieje w bazie – zarezerwowane na przyszłość."""


class UserNotFoundError(Exception):
    """Użytkownik nie istnieje w bazie – zarezerwowane na przyszłość."""
