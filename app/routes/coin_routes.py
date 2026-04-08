"""
Endpointy dla widoków kryptowalut.

Odpowiedzialności warstwy routes:
    - odbieranie requestów HTTP i walidacja parametrów URL/query
    - delegowanie logiki do coin_service
    - renderowanie szablonów HTML lub zwracanie JSON
    - obsługa kodów HTTP (404, 400)

Nie odpowiada za:
    - logikę biznesową (coin_service)
    - zapytania SQL (repozytoria)
    - throttling, ensure_history, cleanup (coin_service)

Routes:
    GET /coins/                       – lista top 20 monet z aktualnymi cenami
    GET /coins/<id>                   – szczegóły monety (chart_data puste, JS pobiera AJAX)
    GET /coins/<id>/history?range=Xd  – AJAX: zwraca historię dla zakresu 24h/7d/30d
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, abort, jsonify, request
from flask_login import current_user

from app.repositories import price_history_repository, portfolio_repository
from app.services import coin_service

coin_bp = Blueprint("coins", __name__, url_prefix="/coins")

WARSAW = ZoneInfo("Europe/Warsaw")

RANGE_DAYS: dict[str, int] = {
    "24h": 1,
    "7d": 7,
    "30d": 30,
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@coin_bp.route("/")
def list_coins():
    """
    Wyświetla listę top 20 kryptowalut z aktualnymi cenami.

    Deleguje odświeżenie cen do coin_service.update_prices() który ma
    wbudowany throttling – CoinGecko odpytywane max raz na 5 minut.

    Returns:
        Wyrenderowany szablon coins/list.html z listą monet.
    """
    coin_service.update_prices()
    coins = coin_service.get_all_coins()
    return render_template("coins/list.html", coins=coins)


@coin_bp.route("/<int:coin_id>")
def detail(coin_id: int):
    """
    Wyświetla stronę szczegółową monety.

    chart_data=[] – dane wykresu pobierane przez AJAX w price_chart.js
    zaraz po załadowaniu strony (setRange("30d")). Strona ładuje się
    szybko, wykres renderuje się asynchronicznie.

    Deleguje czyszczenie starej historii do coin_service.cleanup_coin_history()
    z wbudowanym throttlingiem (max raz na 24h per-moneta).

    Args:
        coin_id: Klucz główny monety z URL.

    Returns:
        Wyrenderowany szablon coins/detail.html lub 404 jeśli moneta nie istnieje.
    """
    coin = coin_service.get_coin_by_id(coin_id)
    if coin is None:
        abort(404)

    coin_service.cleanup_coin_history(coin_id, days=30)

    holding = None
    if current_user.is_authenticated:
        holding = portfolio_repository.find_by_user_and_coin(
            current_user.id, coin_id
        )

    return render_template(
        "coins/detail.html",
        coin=coin,
        chart_data=[],  # JS pobierze przez AJAX → setRange("30d")
        holding=holding,
    )


@coin_bp.route("/<int:coin_id>/history")
def history_api(coin_id: int):
    """
    AJAX endpoint – zwraca historię cen dla wybranego zakresu czasowego.

    Wywoływany przez price_chart.js przy zmianie zakresu wykresu.
    Deleguje uzupełnianie brakującej historii do coin_service.ensure_history()
    (max 1 zapytanie do CoinGecko co 10 min).

    Query params:
        range: "24h" | "7d" | "30d"  (domyślnie "24h")

    Returns:
        JSON: lista obiektów { ts, label, price } gotowych dla Chart.js.
        ts    – Unix timestamp w sekundach (JS mnoży przez 1000 przy filtracji)
        label – sformatowana etykieta osi X w czasie warszawskim
        price – cena w USD

    Status codes:
        200 – dane zwrócone poprawnie
        400 – nieprawidłowy parametr range
        404 – moneta nie istnieje
    """
    range_key = request.args.get("range", "24h")
    if range_key not in RANGE_DAYS:
        return jsonify({"error": "invalid range"}), 400

    coin = coin_service.get_coin_by_id(coin_id)
    if coin is None:
        return jsonify({"error": "not found"}), 404

    days = RANGE_DAYS[range_key]
    coin_service.ensure_history(coin, days=days)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    history = price_history_repository.find_since(coin_id, since=since)
    return jsonify(_build_chart_data(history))


# ---------------------------------------------------------------------------
# Pomocnik prywatny – formatowanie danych dla Chart.js
# ---------------------------------------------------------------------------

def _build_chart_data(history) -> list[dict]:
    """
    Konwertuje listę obiektów PriceHistory na listę słowników dla Chart.js.

    Należy do warstwy routes – formatuje dane do odpowiedzi HTTP/JSON.
    Logika biznesowa (filtrowanie, zapewnienie historii) jest w coin_service.

    ts zwracane w sekundach (Unix timestamp) – price_chart.js mnoży przez
    1000 przy porównaniu z Date.now() który jest w milisekundach.

    Args:
        history: Lista obiektów PriceHistory pobranych z bazy.

    Returns:
        Lista słowników z kluczami ts, label, price.
    """
    return [
        {
            "ts": int(h.recorded_at.replace(tzinfo=timezone.utc).timestamp()),
            "label": (
                h.recorded_at
                .replace(tzinfo=timezone.utc)
                .astimezone(WARSAW)
                .strftime("%d.%m %H:%M")
            ),
            "price": h.price_usd,
        }
        for h in history
    ]
