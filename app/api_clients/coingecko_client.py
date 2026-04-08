"""
Klient HTTP do komunikacji z CoinGecko API.

Dokumentacja API: https://docs.coingecko.com/reference/introduction
Plan darmowy (Demo): 30 req/min, 10 000 req/miesiąc.

Klucz API odczytywany z konfiguracji Flaska (current_app.config)
i przekazywany w nagłówku x-cg-demo-api-key.
Bez klucza zapytania idą anonimowo (niestabilny limit ~5–15 req/min).

Używany przez:
    - coin_service.update_prices()    – pobiera aktualne ceny
    - coin_service.ensure_history()   – pobiera historię dla wykresu
"""
import httpx
from flask import current_app

from app.exceptions import ExternalAPIError

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINS_TO_FETCH = 20


def _get_headers() -> dict:
    """
    Buduje nagłówki HTTP dla zapytania do CoinGecko.

    Jeśli w konfiguracji Flaska ustawiony jest COINGECKO_API_KEY,
    dodaje go jako nagłówek x-cg-demo-api-key (wymagany przez plan Demo).

    Returns:
        Słownik nagłówków – pusty dict jeśli brak klucza API.
    """
    headers: dict = {}
    api_key = current_app.config.get("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    return headers


def get_top_coins() -> list[dict]:
    """
    Pobiera listę top N kryptowalut według kapitalizacji rynkowej.

    Używa endpointu /coins/markets który zwraca dane dla wielu monet
    w jednym zapytaniu – oszczędza limit API.

    Returns:
        Lista słowników z polami:
            id                          – identyfikator CoinGecko, np. "bitcoin"
            symbol                      – ticker, np. "btc"
            name                        – pełna nazwa, np. "Bitcoin"
            current_price               – aktualna cena w USD
            market_cap                  – kapitalizacja rynkowa w USD
            price_change_percentage_24h – zmiana ceny w ciągu 24h (%)

    Raises:
        ExternalAPIError: gdy zapytanie HTTP się nie powiedzie.
    """
    url = f"{COINGECKO_BASE}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": COINS_TO_FETCH,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params, headers=_get_headers())
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise ExternalAPIError(f"CoinGecko API error: {e}") from e


def get_coin_history(coingecko_id: str, days: int = 30) -> list[list[float]]:
    """
    Pobiera historię cen danej kryptowaluty.

    Granulacja zwracanych danych zależy od zakresu (ustalana przez API):
        1 dzień   → dane co ~5 minut
        2–90 dni  → dane co godzinę
        >90 dni   → dane dzienne

    Typ zwracany list[list[float]] – nie list[tuple]:
        JSON nie ma tupli – API zwraca tablice tablic np.:
        [[1711929600000.0, 50000.12], [1711933200000.0, 50234.55], ...]
        Python deserializuje tablice JSON jako list, nie tuple.
        Użycie: for timestamp_ms, price in raw_history – działa z list[list].

    Args:
        coingecko_id: Identyfikator monety w CoinGecko, np. "bitcoin".
        days:         Liczba dni historii do pobrania (domyślnie 30).

    Returns:
        Lista list [timestamp_ms, price_usd] posortowanych rosnąco po czasie.
        timestamp_ms – Unix timestamp w milisekundach (float z JSON).
        price_usd    – cena w USD (float).

    Raises:
        ExternalAPIError: gdy zapytanie HTTP się nie powiedzie.
    """
    url = f"{COINGECKO_BASE}/coins/{coingecko_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": days,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params, headers=_get_headers())
            response.raise_for_status()
            data = response.json()
            return data.get("prices", [])
    except httpx.HTTPError as e:
        raise ExternalAPIError(f"CoinGecko API error: {e}") from e
