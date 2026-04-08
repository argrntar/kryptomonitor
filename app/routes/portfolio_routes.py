"""
Endpointy portfela użytkownika.

Odpowiedzialności warstwy routes:
    - odbieranie requestów HTTP i walidacja parametrów (page, CSRF)
    - delegowanie logiki i agregacji danych do portfolio_service
    - formatowanie odpowiedzi (renderowanie szablonów, CSV, redirecty)
    - obsługa flash messages

Nie odpowiada za:
    - obliczenia P&L – portfolio_service.build_positions()
    - agregację danych dla szablonów – portfolio_service.get_dashboard_data()
    - zapytania SQL – repozytoria (wywoływane przez serwis)
    - logikę kupna/sprzedaży – portfolio_service.buy(), sell(), close_all()

Routes:
    GET  /portfolio/                – dashboard z pozycjami i ostatnimi 10 transakcjami
    GET  /portfolio/history         – pełna historia transakcji z paginacją
    GET  /portfolio/history/export  – pobieranie historii jako plik CSV
    POST /portfolio/close-all       – sprzedaż wszystkich pozycji (wymaga CSRF)
"""
import csv
import io
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, Response, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf import FlaskForm

from app.services import portfolio_service

portfolio_bp = Blueprint("portfolio", __name__, url_prefix="/portfolio")
WARSAW = ZoneInfo("Europe/Warsaw")


@portfolio_bp.route("/")
@login_required
def dashboard():
    """
    Dashboard portfela – otwarte pozycje, P&L i ostatnie 10 transakcji.

    Deleguje całą logikę agregacji do portfolio_service.get_dashboard_data().
    Route odpowiada tylko za przekazanie danych do szablonu.

    Wyświetla link do pełnej historii gdy jest więcej niż 10 transakcji.
    """
    data = portfolio_service.get_dashboard_data(current_user.id)
    return render_template(
        "portfolio/dashboard.html",
        **data,
        balance_usd=current_user.balance_usd,
        close_form=FlaskForm(),
    )


@portfolio_bp.route("/history")
@login_required
def history():
    """
    Pełna historia transakcji z paginacją.

    15 transakcji na stronę – mieści się na Full HD bez przewijania.
    Deleguje pobieranie i paginację do portfolio_service.get_history_page().
    """
    page = request.args.get("page", 1, type=int)
    data = portfolio_service.get_history_page(current_user.id, page=page)
    return render_template("portfolio/history.html", **data)


@portfolio_bp.route("/history/export")
@login_required
def export_csv():
    """
    Pobieranie pełnej historii transakcji jako plik CSV.

    Dane (transakcje + mapa monet) dostarcza portfolio_service.get_export_data().
    Formatowanie CSV (nagłówki, wiersze, konwersja dat) należy do routes –
    to warstwa prezentacji, nie logika biznesowa.

    Używa biblioteki standardowej csv – zero dodatkowych zależności.
    """
    transactions, coins_map = portfolio_service.get_export_data(current_user.id)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Data", "Typ", "Symbol", "Nazwa", "Ilość", "Cena (USD)", "Wartość (USD)"
    ])

    for tx in transactions:
        coin = coins_map.get(tx.coin_id)
        dt = tx.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_local = dt.astimezone(WARSAW).strftime("%d.%m.%Y %H:%M")

        # Wartość: ujemna dla KUP (wydatek), dodatnia dla SPRZEDAJ (przychód)
        # Spójne z widokiem w aplikacji gdzie KUP = czerwony minus, SPRZEDAJ = zielony plus
        value = tx.total_usd if tx.transaction_type == "sell" else -tx.total_usd

        writer.writerow([
            dt_local,
            "KUP" if tx.transaction_type == "buy" else "SPRZEDAJ",
            coin.symbol if coin else "?",
            coin.name if coin else "?",
            f"{tx.amount:.4f}",
            f"{tx.price_usd:.4f}",
            f"{value:.2f}",
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=historia_transakcji.csv"
        },
    )


@portfolio_bp.route("/close-all", methods=["POST"])
@login_required
def close_all():
    """
    Sprzedaje wszystkie otwarte pozycje po aktualnych cenach.

    Wymaga metody POST z ważnym tokenem CSRF (FlaskForm.validate_on_submit()).
    Deleguje logikę sprzedaży do portfolio_service.close_all() który
    zapisuje wszystkie sprzedaże w jednej atomowej transakcji bazodanowej.
    """
    form = FlaskForm()
    if not form.validate_on_submit():
        flash("Nieprawidłowe żądanie.", "danger")
        return redirect(url_for("portfolio.dashboard"))

    sold, skipped = portfolio_service.close_all(current_user)

    if sold > 0 and skipped == 0:
        flash(f"Zamknięto {sold} pozycji. Całość sprzedana po aktualnych cenach.", "success")
    elif sold > 0 and skipped > 0:
        flash(f"Zamknięto {sold} pozycji. Pominięto {skipped} (brak aktualnej ceny).", "warning")
    else:
        flash("Brak pozycji do zamknięcia.", "info")

    return redirect(url_for("portfolio.dashboard"))
