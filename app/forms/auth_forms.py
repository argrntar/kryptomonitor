"""
Formularze WTForms dla autoryzacji i edycji profilu.

Klasy:
    RegisterForm    – rejestracja nowego użytkownika
    LoginForm       – logowanie z opcją "zapamiętaj mnie"
    EditProfileForm – edycja danych profilu i zmiana hasła

Walidacja unikalności:
    Walidatory validate_username() i validate_email() wołają funkcje
    modułowe z user_repository – NIE tworzą instancji UserRepository.
    Formularze mogą wołać repozytoria bezpośrednio tylko w walidatorach
    (sprawdzanie unikalności jest ściśle związane z formularzem).
    Nie wołają serwisu ponieważ to nie jest operacja biznesowa –
    to walidacja danych wejściowych przed wysłaniem do serwisu.
"""
from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional, ValidationError
)

from app.repositories.user_repository import username_exists, email_exists


class RegisterForm(FlaskForm):
    username = StringField(
        "Nazwa użytkownika",
        validators=[
            DataRequired(message="Pole wymagane."),
            Length(min=3, max=64, message="Od 3 do 64 znaków."),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Pole wymagane."),
            Email(message="Nieprawidłowy adres email."),
            Length(max=120),
        ],
    )
    password = PasswordField(
        "Hasło",
        validators=[
            DataRequired(message="Pole wymagane."),
            Length(min=8, message="Minimum 8 znaków."),
        ],
    )
    password_confirm = PasswordField(
        "Potwierdź hasło",
        validators=[
            DataRequired(message="Pole wymagane."),
            EqualTo("password", message="Hasła muszą być identyczne."),
        ],
    )
    submit = SubmitField("Zarejestruj się")

    def validate_username(self, field):
        """Sprawdza czy nazwa użytkownika jest już zajęta."""
        if username_exists(field.data):
            raise ValidationError("Ta nazwa użytkownika jest już zajęta.")

    def validate_email(self, field):
        """Sprawdza czy adres email jest już zarejestrowany."""
        if email_exists(field.data):
            raise ValidationError("Ten adres email jest już zarejestrowany.")


class LoginForm(FlaskForm):
    username = StringField(
        "Nazwa użytkownika",
        validators=[DataRequired(message="Pole wymagane.")],
    )
    password = PasswordField(
        "Hasło",
        validators=[DataRequired(message="Pole wymagane.")],
    )
    remember = BooleanField("Zapamiętaj mnie")
    submit = SubmitField("Zaloguj się")


class EditProfileForm(FlaskForm):
    """
    Formularz edycji profilu użytkownika.

    Dane podstawowe (username, email) są zawsze edytowalne.
    Zmiana hasła jest opcjonalna – pola hasła są wymagane
    tylko gdy użytkownik chce zmienić hasło (podał nowe hasło).

    Walidacja unikalności username i email pomija aktualnego
    użytkownika – można "zapisać" bez zmian bez błędu walidacji.
    """
    username = StringField(
        "Nazwa użytkownika",
        validators=[
            DataRequired(message="Pole wymagane."),
            Length(min=3, max=64, message="Od 3 do 64 znaków."),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Pole wymagane."),
            Email(message="Nieprawidłowy adres email."),
            Length(max=120),
        ],
    )
    current_password = PasswordField(
        "Aktualne hasło",
        validators=[Optional()],
    )
    new_password = PasswordField(
        "Nowe hasło",
        validators=[
            Optional(),
            Length(min=8, message="Minimum 8 znaków."),
        ],
    )
    new_password_confirm = PasswordField(
        "Potwierdź nowe hasło",
        validators=[
            Optional(),
            EqualTo("new_password", message="Hasła muszą być identyczne."),
        ],
    )
    submit = SubmitField("Zapisz zmiany")

    def validate_username(self, field):
        """Sprawdza unikalność – pomija aktualnego użytkownika."""
        if field.data != current_user.username and username_exists(field.data):
            raise ValidationError("Ta nazwa użytkownika jest już zajęta.")

    def validate_email(self, field):
        """Sprawdza unikalność – pomija aktualnego użytkownika."""
        if field.data != current_user.email and email_exists(field.data):
            raise ValidationError("Ten adres email jest już zarejestrowany.")

    def validate_current_password(self, field):
        """Aktualne hasło wymagane tylko gdy podano nowe hasło."""
        if self.new_password.data and not field.data:
            raise ValidationError("Podaj aktualne hasło aby je zmienić.")
