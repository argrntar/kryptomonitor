"""
Blueprint główny (Main Blueprint).

Obsługuje trasy niezwiązane z konkretnym modułem aplikacji:
    /  → redirect na listę kryptowalut

Dlaczego osobny blueprint zamiast @app.route() w create_app()?
──────────────────────────────────────────────────────────────
Dokumentacja Flask zaleca rejestrowanie widoków w blueprintach
zamiast bezpośrednio w fabryce aplikacji:
https://flask.palletsprojects.com/en/stable/tutorial/views/

Dzięki temu create_app() zajmuje się wyłącznie konfiguracją
i rejestracją komponentów, a logika tras jest w osobnych modułach.

W przyszłości main_bp może przejąć inne trasy ogólne:
    /about, /kontakt, /ping (health check),
    error handlery 404/500, itp.
"""
from flask import Blueprint, redirect, url_for

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Przekierowuje root URL na listę kryptowalut."""
    return redirect(url_for("coins.list_coins"))
