"""
Konfiguracja aplikacji (Configuration Pattern).

Standard: klasy konfiguracji dziedziczące po Config bazowym.
Dokumentacja Flask: https://flask.palletsprojects.com/en/stable/config/

Środowiska:
    Config            – bazowa konfiguracja wspólna dla wszystkich środowisk
    DevelopmentConfig – SQLite, DEBUG=True (domyślna)
    TestingConfig     – SQLite :memory:, TESTING=True
    ProductionConfig  – PostgreSQL, DEBUG=False

Przełączanie środowisk:
    Nazwa configu przekazywana jest jawnie w miejscu wywołania:
        run.py:           create_app()             → DevelopmentConfig
        conftest.py:      create_app("testing")    → TestingConfig
        gunicorn:         create_app("production") → ProductionConfig

    FLASK_ENV jest deprecated od Flask 2.3 i usunięte w Flask 2.3+.
    Źródło: https://flask.palletsprojects.com/en/stable/changes/

Dlaczego .env zamiast hardcoded wartości?
─────────────────────────────────────────
Metodologia 12-Factor App (https://12factor.net/config):
"Konfiguracja która różni się między środowiskami powinna być
przechowywana w zmiennych środowiskowych, nie w kodzie."

Klucz API w kodzie = klucz widoczny dla każdego kto ma dostęp do repo.
Git jest trwały – nawet po usunięciu pliku klucz zostaje w historii.

Wzorzec .env / .env.example:
    .env.example – w repo, puste wartości (dokumentacja zmiennych)
    .env         – w .gitignore, prawdziwe klucze (nigdy w repo)

    Źródło konwencji:
        - 12-Factor App: https://12factor.net/config
        - python-dotenv: https://github.com/theskumar/python-dotenv

Dlaczego dotenv_values() zamiast load_dotenv() + os.environ?
──────────────────────────────────────────────────────────────
load_dotenv() wstrzykuje zmienne do os.environ – globalnego słownika procesu.
dotenv_values() zwraca zwykły dict – nie modyfikuje środowiska systemu.
Czystsze i bardziej przewidywalne w aplikacjach Flask.

Źródło: https://github.com/theskumar/python-dotenv
"dotenv_values works more or less the same way as load_dotenv,
 except it doesn't touch the environment."
"""
from datetime import timedelta
from pathlib import Path

from dotenv import dotenv_values

# BASE_DIR – katalog główny projektu (rodzic katalogu app/)
# Path(__file__) → app/config.py
# .parent        → app/
# .parent        → katalog główny projektu ← BASE_DIR
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)  # tworzy data/ automatycznie przy imporcie
DATABASE = "cryptomonitor.db"

# Odczytaj .env jako słownik – nie modyfikuje os.environ.
# Jeśli .env nie istnieje, dotenv_values() zwraca pusty dict
# i używane są wartości domyślne zdefiniowane w .get().
_env = dotenv_values(BASE_DIR / ".env")


class Config:
    """
    Bazowa konfiguracja wspólna dla wszystkich środowisk.

    Wartości wrażliwe (SECRET_KEY, COINGECKO_API_KEY, DATABASE_URL)
    odczytywane z pliku .env przez dotenv_values(). Jeśli .env
    nie istnieje lub klucz nie jest ustawiony – używana jest wartość
    domyślna.
    """

    # ------------------------------------------------------------------
    # SECRET_KEY
    # Używany przez Flask do podpisywania sesji i tokenów CSRF.
    # W produkcji MUSI być losowy i tajny.
    # Dokumentacja: https://flask.palletsprojects.com/en/stable/config/
    # ------------------------------------------------------------------
    SECRET_KEY = _env.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # ------------------------------------------------------------------
    # Baza danych
    # Domyślnie SQLite – plik data/cryptomonitor.db w katalogu głównym.
    # ProductionConfig nadpisuje na PostgreSQL przez DATABASE_URL w .env.
    #
    # Format URI:
    #   sqlite:///   → ścieżka względna od katalogu roboczego
    #   postgresql://user:pass@host:port/dbname
    # Źródło: https://flask-sqlalchemy.readthedocs.io/en/stable/config/
    # ------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _env.get(
        "DATABASE_URL",
        f"sqlite:///{DATA_DIR / DATABASE}",
    )

    # Wyłącza śledzenie modyfikacji obiektów – zbędny narzut pamięciowy.
    # Źródło: https://flask-sqlalchemy.readthedocs.io/en/stable/config/
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Włącza ochronę CSRF dla formularzy WTForms.
    WTF_CSRF_ENABLED = True

    # ------------------------------------------------------------------
    # CoinGecko API
    # Klucz API wymagany dla stabilnego limitu 30 req/min.
    # Bez klucza działa z niestabilnym limitem ~5–15 req/min.
    # Darmowy klucz: https://www.coingecko.com/pl/api/pricing
    # ------------------------------------------------------------------
    COINGECKO_API_KEY = _env.get("COINGECKO_API_KEY", "")

    # Czas życia ciasteczka "zapamiętaj mnie" w Flask-Login.
    REMEMBER_COOKIE_DURATION = timedelta(days=30)


class DevelopmentConfig(Config):
    """
    Konfiguracja deweloperska – domyślna.

    DEBUG = True włącza:
        - automatyczny restart serwera po zmianach plików (Werkzeug reloader)
        - interaktywny debugger w przeglądarce przy błędach
        - szczegółowe komunikaty błędów

    NIGDY nie używać DEBUG = True w produkcji.
    Źródło: https://flask.palletsprojects.com/en/stable/config/
    """
    DEBUG = True


class TestingConfig(Config):
    """
    Konfiguracja do testów (pytest).

    TESTING = True:
        Wyjątki propagują się do testu zamiast zwracać stronę błędu.
        Źródło: https://flask.palletsprojects.com/en/stable/config/

    SQLite :memory::
        Baza w pamięci RAM – szybka, izolowana, znika po teście.
        Nie dotyka bazy deweloperskiej (data/cryptomonitor.db).

    WTF_CSRF_ENABLED = False:
        Testy POST nie muszą generować tokenu CSRF.

    Przykład użycia z pytest:

        @pytest.fixture
        def app():
            app = create_app("testing")
            with app.app_context():
                db.create_all()
                yield app
                db.drop_all()

        @pytest.fixture
        def client(app):
            return app.test_client()

    Źródło: https://flask.palletsprojects.com/en/stable/testing/
    """
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """
    Konfiguracja produkcyjna – PostgreSQL.

    Wymaga zmiennej DATABASE_URL w .env:
        DATABASE_URL=postgresql://user:pass@host:5432/crypto_monitor

    Wymaga zainstalowanego drivera:
        pip install psycopg2-binary

    SQLALCHEMY_ENGINE_OPTIONS:
        pool_pre_ping=True   – testuje połączenie przed użyciem,
                               zapobiega błędom "server closed connection"
        pool_recycle=1800    – recykluje połączenia starsze niż 30 minut
        pool_size=10         – max 10 połączeń w puli (domyślnie 5)
        max_overflow=20      – dodatkowe połączenia przy szczytowym obciążeniu

    Uruchomienie:
        flask db upgrade
        gunicorn -w 4 "app:create_app('production')"

    Dokumentacja puli połączeń:
        https://docs.sqlalchemy.org/en/20/core/pooling.html
    """
    DEBUG = False

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_size": 10,
        "max_overflow": 20,
    }


# ------------------------------------------------------------------
# Słownik konfiguracji używany przez create_app() w app/__init__.py:
#   app.config.from_object(config[config_name])
#
# Klucz "default" → DevelopmentConfig, używany gdy create_app()
# wywołane bez argumentu.
# ------------------------------------------------------------------
config = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
