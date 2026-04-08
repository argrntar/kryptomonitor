"""
Endpointy autoryzacji i zarządzania kontem.

Odpowiedzialności warstwy routes:
    - odbieranie requestów HTTP, walidacja formularzy
    - delegowanie logiki do auth_service (funkcje modułowe)
    - flash messages, redirecty

Nie odpowiada za:
    - logikę rejestracji / logowania – auth_service
    - hashowanie haseł – auth_service
    - zapytania SQL – user_repository

Routes:
    GET/POST /auth/register       – rejestracja
    GET/POST /auth/login          – logowanie (z "zapamiętaj mnie")
    GET      /auth/logout         – wylogowanie
    GET/POST /auth/profile        – edycja profilu i zmiana hasła
    POST     /auth/delete-account – usunięcie konta (wymaga potwierdzenia hasłem)
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm

from app.forms.auth_forms import RegisterForm, LoginForm, EditProfileForm
from app.services import auth_service

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Rejestracja nowego użytkownika.

    GET  – wyświetla formularz rejestracji.
    POST – waliduje dane, deleguje zapis do auth_service.register(),
           loguje nowego użytkownika i przekierowuje na listę monet.
    """
    if current_user.is_authenticated:
        return redirect(url_for("coins.list_coins"))

    form = RegisterForm()
    if form.validate_on_submit():
        user = auth_service.register(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data,
        )
        login_user(user)
        flash(f"Konto zostało utworzone. Witaj, {user.username}!", "success")
        return redirect(url_for("coins.list_coins"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Logowanie użytkownika.

    GET  – wyświetla formularz logowania.
    POST – weryfikuje dane przez auth_service.authenticate().

    Parametr remember=True powoduje zapisanie trwałego ciasteczka –
    użytkownik pozostaje zalogowany po zamknięciu przeglądarki.
    Czas życia ciasteczka kontroluje REMEMBER_COOKIE_DURATION w config.py.
    """
    if current_user.is_authenticated:
        return redirect(url_for("coins.list_coins"))

    form = LoginForm()
    if form.validate_on_submit():
        user = auth_service.authenticate(
            username=form.username.data,
            password=form.password.data,
        )
        if user is None:
            flash("Nieprawidłowa nazwa użytkownika lub hasło.", "danger")
            return redirect(url_for("auth.login"))

        login_user(user, remember=form.remember.data)
        flash(f"Witaj, {user.username}!", "success")
        return redirect(url_for("coins.list_coins"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    """Wylogowanie – usuwa sesję i trwałe ciasteczko."""
    logout_user()
    flash("Zostałeś wylogowany.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Edycja profilu użytkownika.

    GET  – formularz wypełniony aktualnymi danymi użytkownika.
    POST – deleguje zapis do auth_service.update_profile().
           Zmiana hasła opcjonalna – pola hasła można zostawić puste.
    """
    form = EditProfileForm(obj=current_user)

    if form.validate_on_submit():
        success, message = auth_service.update_profile(
            user=current_user,
            username=form.username.data,
            email=form.email.data,
            current_password=form.current_password.data or "",
            new_password=form.new_password.data or "",
        )
        flash(message, "success" if success else "danger")
        if success:
            return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", form=form, delete_form=FlaskForm())


@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    """
    Trwale usuwa konto zalogowanego użytkownika.

    Wymaga metody POST z ważnym tokenem CSRF (FlaskForm)
    oraz potwierdzenia hasłem w polu formularza.

    Cascade delete w modelach automatycznie usuwa portfolio i transakcje.
    Po usunięciu użytkownik jest wylogowywany i przekierowywany na stronę logowania.
    """
    form = FlaskForm()
    if not form.validate_on_submit():
        flash("Nieprawidłowe żądanie.", "danger")
        return redirect(url_for("auth.profile"))

    password = request.form.get("confirm_password", "")
    user = current_user._get_current_object()

    success, message = auth_service.delete_account(user, password)

    if not success:
        flash(message, "danger")
        return redirect(url_for("auth.profile"))

    logout_user()
    flash("Konto zostało trwale usunięte.", "info")
    return redirect(url_for("auth.login"))
