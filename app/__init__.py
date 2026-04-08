"""
Fabryka aplikacji Flask (Application Factory Pattern).

Wzorzec Application Factory jest oficjalnym standardem Flask opisanym
w dokumentacji: https://flask.palletsprojects.com/en/stable/patterns/appfactories/

Zalety wzorca:
    - wiele instancji aplikacji w jednym procesie (np. testy)
    - konfiguracja wstrzykiwana z zewnątrz zamiast hardcoded
    - brak circular imports – extensions inicjalizowane w create_app()

Kolejność inicjalizacji (ważna – nie zmieniać):
    1. Stwórz app i wczytaj konfigurację
    2. Zainicjalizuj extensions (db, migrate, login_manager)
    3. Zaimportuj modele (wymagane przez Alembic i Flask-Login)
    4. Zarejestruj user_loader dla Flask-Login
    5. Zarejestruj filtry Jinja2
    6. Zarejestruj blueprinty
    7. Sprawdź konfigurację i wyświetl ostrzeżenia

Zarządzanie schematem bazy danych:
    Schemat zarządzany przez Flask-Migrate (Alembic).
    db.create_all() NIE jest używane – migracje przejmują pełną
    kontrolę nad tworzeniem i modyfikacją tabel.

    Komendy migracji:
        flask db init              – jednorazowo, tworzy katalog migrations/
        flask db migrate -m "opis" – generuje migrację z modeli
        flask db upgrade           – aplikuje migracje na bazę danych

    render_as_batch=True jest ustawione w extensions.py przy tworzeniu
    instancji Migrate – wymagane dla SQLite.
"""
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import Flask

from app.config import config
from app.extensions import db, migrate, login_manager

WARSAW = ZoneInfo("Europe/Warsaw")


def create_app(config_name: str = "default") -> Flask:
    """
    Tworzy i konfiguruje instancję aplikacji Flask.

    Args:
        config_name: Klucz słownika config z app/config.py.
                     Domyślnie "default" → DevelopmentConfig.
                     Przekazywany jawnie w miejscu wywołania:
                         run.py:       create_app()
                         conftest.py:  create_app("testing")
                         gunicorn:     create_app("production")

    Returns:
        Skonfigurowana instancja Flask gotowa do uruchomienia.
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ------------------------------------------------------------------
    # Krok 1 – Extensions
    # Inicjalizacja przez init_app() – standard Flask Application Factory.
    # Źródło: https://flask.palletsprojects.com/en/stable/extensions/
    #
    # Kolejność ma znaczenie:
    #   db       → musi być pierwszy (inne rozszerzenia zależą od bazy)
    #   migrate  → wymaga db i app (zarządza schematem przez Alembic)
    #   login    → wymaga app (konfiguruje sesje użytkowników)
    # ------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # ------------------------------------------------------------------
    # Krok 2 – Modele
    # Import wymagany żeby Alembic widział wszystkie tabele przy
    # generowaniu migracji (flask db migrate).
    # noqa: F401 – importy "unused" są tu celowe (efekt uboczny importu
    # rejestruje modele w SQLAlchemy metadata).
    # ------------------------------------------------------------------
    from app.models import User, Coin, PriceHistory, Portfolio, Transaction  # noqa: F401

    # ------------------------------------------------------------------
    # Krok 3 – Flask-Login user_loader
    # Callback wywoływany przy każdym requeście dla zalogowanego
    # użytkownika – ładuje obiekt User z bazy na podstawie ID z sesji.
    #
    # db.session.get() – nowe API SQLAlchemy 2.0 (query.get() jest legacy).
    # Źródło: https://flask-login.readthedocs.io/
    # ------------------------------------------------------------------
    from app.models.user import User as UserModel

    @login_manager.user_loader
    def load_user(user_id: str) -> UserModel | None:
        return db.session.get(UserModel, int(user_id))

    # ------------------------------------------------------------------
    # Krok 4 – Filtry Jinja2
    # localdt: konwertuje datetime UTC → czas warszawski (Europe/Warsaw).
    # ZoneInfo (PEP 615, Python 3.9+) – standardowa biblioteka,
    # obsługuje automatycznie zmianę czasu letniego/zimowego.
    #
    # Użycie w szablonie: {{ coin.last_updated | localdt }}
    # Zwraca: "28.03.2026 14:30"
    # ------------------------------------------------------------------
    @app.template_filter("localdt")
    def localdt_filter(dt) -> str:
        """Konwertuje datetime UTC na czas warszawski DD.MM.YYYY HH:MM."""
        if dt is None:
            return "—"
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(WARSAW).strftime("%d.%m.%Y %H:%M")

    # ------------------------------------------------------------------
    # Krok 5 – Blueprinty
    # Import wewnątrz funkcji zapobiega circular imports.
    # Każdy blueprint enkapsuluje powiązane endpointy.
    # Źródło: https://flask.palletsprojects.com/en/stable/blueprints/
    # ------------------------------------------------------------------
    from app.routes.auth_routes import auth_bp
    from app.routes.coin_routes import coin_bp
    from app.routes.main_routes import main_bp
    from app.routes.portfolio_routes import portfolio_bp
    from app.routes.trade_routes import trade_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(coin_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(portfolio_bp)

    # ------------------------------------------------------------------
    # Krok 6 – Ostrzeżenia konfiguracyjne
    # Widoczne w terminalu przy starcie serwera.
    # WARNING jest domyślnie widoczny bez dodatkowej konfiguracji logowania.
    # Źródło: https://flask.palletsprojects.com/en/stable/logging/
    # ------------------------------------------------------------------
    if not app.config.get("COINGECKO_API_KEY"):
        app.logger.warning(
            "COINGECKO_API_KEY nie ustawiony! "
            "Uzupełnij plik .env. "
            "Bez klucza limit CoinGecko jest niestabilny (~5–15 req/min). "
            "Darmowy klucz: https://www.coingecko.com/pl/api/pricing"
        )

    # ------------------------------------------------------------------
    # Krok 7 – Testy: twórz tabele bezpośrednio (bez migracji)
    # W TestingConfig używamy SQLite :memory: – Alembic jest zbędny.
    # db.create_all() tworzy tabele na podstawie modeli w pamięci RAM.
    # ------------------------------------------------------------------
    if app.config.get("testing"):
        with app.app_context():
            db.create_all()

    return app
