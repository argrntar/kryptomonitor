"""
Endpointy dla operacji handlowych (kupno / sprzedaż kryptowalut).

Odpowiedzialności warstwy routes:
    - odbieranie requestów HTTP, walidacja formularzy
    - delegowanie operacji do portfolio_service (buy, sell)
    - delegowanie obliczenia minimalnej ilości do portfolio_service
    - flash messages, redirecty

Nie odpowiada za:
    - logikę kupna/sprzedaży – portfolio_service.buy(), sell()
    - obliczenia Decimal (min_amount) – portfolio_service.get_min_sell_amount()
    - zapytania SQL – portfolio_repository (przez serwis)

Routes:
    GET  /trade/<coin_id>       – formularz kupna i sprzedaży
    POST /trade/<coin_id>/buy   – wykonanie zakupu
    POST /trade/<coin_id>/sell  – wykonanie sprzedaży
"""
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from app.exceptions import InsufficientFundsError, InsufficientCoinError
from app.forms.trade_forms import BuyForm, SellForm
from app.repositories import portfolio_repository
from app.services import coin_service, portfolio_service

trade_bp = Blueprint("trade", __name__, url_prefix="/trade")


@trade_bp.route("/<int:coin_id>", methods=["GET"])
@login_required
def trade_form(coin_id: int):
    """
    Wyświetla formularz kupna i sprzedaży dla danej monety.

    Deleguje obliczenie minimalnej ilości sprzedaży do
    portfolio_service.get_min_sell_amount() – logika biznesowa
    (MIN_TRANSACTION_USD / price) należy do serwisu, nie do routes.

    Flash informacyjny wyświetlany tylko przy bezpośrednim wejściu
    (nie po redirect z błędu walidacji) – sprawdzane przez ?error=1.
    """
    coin = coin_service.get_coin_by_id(coin_id)
    if coin is None:
        abort(404)

    holding = portfolio_repository.find_by_user_and_coin(current_user.id, coin_id)

    if not request.args.get("error") and holding and holding.amount > 0:
        min_sell = portfolio_service.get_min_sell_amount(coin)

        if min_sell is not None:
            holding_amount = holding.amount
            if holding_amount >= float(min_sell):
                flash(
                    f"Minimalna ilość sprzedaży {coin.symbol} to {min_sell} "
                    f"(wartość transakcji >= $0.01).",
                    "info",
                )
            else:
                flash(
                    f"Posiadasz {holding_amount:.4f} {coin.symbol} w portfelu. "
                    f"Wpisz {holding_amount:.4f} aby sprzedać całość.",
                    "info",
                )

    return render_template(
        "trade/form.html",
        coin=coin,
        buy_form=BuyForm(),
        sell_form=SellForm(),
        holding=holding,
    )


@trade_bp.route("/<int:coin_id>/buy", methods=["POST"])
@login_required
def buy(coin_id: int):
    """
    Wykonuje zakup kryptowaluty.

    Deleguje całą logikę do portfolio_service.buy().
    Route odpowiada tylko za walidację formularza i flash message.
    """
    coin = coin_service.get_coin_by_id(coin_id)
    if coin is None:
        abort(404)

    form = BuyForm()
    if form.validate_on_submit():
        try:
            amount = float(form.amount.data)
            portfolio_service.buy(current_user, coin, amount)
            flash(
                f"Kupiono {amount:.4f} {coin.symbol} "
                f"za ${amount * coin.current_price_usd:,.2f}.",
                "success",
            )
            return redirect(url_for("portfolio.dashboard"))
        except InsufficientFundsError as e:
            flash(str(e), "danger")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")

    return redirect(url_for("trade.trade_form", coin_id=coin_id, error=1))


@trade_bp.route("/<int:coin_id>/sell", methods=["POST"])
@login_required
def sell(coin_id: int):
    """
    Wykonuje sprzedaż kryptowaluty.

    Deleguje całą logikę do portfolio_service.sell().
    Route odpowiada tylko za walidację formularza i flash message.
    """
    coin = coin_service.get_coin_by_id(coin_id)
    if coin is None:
        abort(404)

    form = SellForm()
    if form.validate_on_submit():
        try:
            amount = float(form.amount.data)
            portfolio_service.sell(current_user, coin, amount)
            flash(
                f"Sprzedano {amount:.4f} {coin.symbol} "
                f"za ${amount * coin.current_price_usd:,.2f}.",
                "success",
            )
            return redirect(url_for("portfolio.dashboard"))
        except InsufficientCoinError as e:
            flash(str(e), "danger")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")

    return redirect(url_for("trade.trade_form", coin_id=coin_id, error=1))
