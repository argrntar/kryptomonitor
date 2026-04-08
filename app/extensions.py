"""
Rozszerzenia Flask (Extensions Pattern).

Dokumentacja: https://flask.palletsprojects.com/en/stable/extensions/

Dlaczego extensions w osobnym pliku?
─────────────────────────────────────
Flask oficjalnie zaleca tworzenie instancji rozszerzeń POZA fabryką
aplikacji, a inicjalizację przez init_app() WEWNĄTRZ create_app().
Dzięki temu:
    - brak circular imports (moduły mogą importować db bez importu app)
    - wiele instancji aplikacji w jednym procesie (np. testy)
    - czytelna separacja – wiadomo jakie rozszerzenia używa projekt

Wzorzec:
    1. Tutaj: tworzenie instancji BEZ app (np. db = SQLAlchemy())
    2. W create_app(): inicjalizacja z app (np. db.init_app(app))

Rozszerzenia w tym module:
    db            – SQLAlchemy    – ORM i zarządzanie bazą danych
    migrate       – Flask-Migrate – migracje schematu bazy (Alembic)
    login_manager – Flask-Login   – sesje i autentykacja użytkowników
"""
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# render_as_batch=True – wymagane dla SQLite.
# SQLite nie obsługuje pełnego ALTER TABLE (np. DROP COLUMN, zmiana constraintów).
# Alembic w trybie batch obchodzi to przez stworzenie nowej tabeli,
# skopiowanie danych i zamianę – bez tej opcji przyszłe migracje mogą się wyłożyć.
# Dokumentacja: https://alembic.sqlalchemy.org/en/latest/batch.html
# Flask-Migrate: https://flask-migrate.readthedocs.io/en/latest/
migrate = Migrate(render_as_batch=True)

login_manager = LoginManager()

# ------------------------------------------------------------------
# Konfiguracja Flask-Login
#
# login_view – endpoint do którego Flask-Login przekierowuje
# niezalogowanego użytkownika przy próbie dostępu do widoku
# chronionego dekoratorem @login_required.
#
# login_message – komunikat flash wyświetlany po przekierowaniu.
# login_message_category – kategoria komunikatu używana w szablonach
# do stylowania alertów (warning, info, danger, success).
# ------------------------------------------------------------------
login_manager.login_view = "auth.login"
login_manager.login_message = "Zaloguj się, aby uzyskać dostęp."
login_manager.login_message_category = "warning"
