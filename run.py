"""
Punkt wejścia aplikacji (Entry Point).

Uruchamianie:
    python run.py

Dlaczego load_dotenv() jest PRZED importem create_app()?
─────────────────────────────────────────────────────────
load_dotenv() musi być wywołane zanim cokolwiek z app/ zostanie
zaimportowane. W momencie importu app/config.py wykonywany jest
dotenv_values() który czyta .env. Gdyby load_dotenv() był po
imporcie – .env byłby już załadowany przez config.py i wywołanie
tutaj byłoby zbędne. Kolejność jest celowa.

Dlaczego plik .env nie trafia do repozytorium?
───────────────────────────────────────────────
Plik .env zawiera tajne klucze (SECRET_KEY, COINGECKO_API_KEY).
Jest dodany do .gitignore i NIGDY nie wrzucany do repozytorium.

Profesjonalne rozwiązanie – plik .env.example:
    1. Do repo wrzucamy .env.example z pustymi wartościami:
           COINGECKO_API_KEY=
           SECRET_KEY=
    2. W README piszemy: "Skopiuj .env.example → .env i uzupełnij klucze"
    3. Każdy developer ma swój lokalny .env z własnymi kluczami

Dzięki temu:
    - klucze są bezpieczne (nie w repo)
    - nowy developer wie co uzupełnić (.env.example)
    - aplikacja działa lokalnie bez dodatkowej konfiguracji systemu

Zarządzanie bazą danych:
    Schemat bazy zarządzany przez Flask-Migrate (Alembic).
    Po sklonowaniu repozytorium wykonaj:
        flask db upgrade
    To stworzy bazę danych i wszystkie tabele na podstawie
    plików migracji z katalogu migrations/versions/.

Wybór konfiguracji przez FLASK_CONFIG:
───────────────────────────────────────
Środowisko wybierane jest przez zmienną FLASK_CONFIG:
    development  → DevelopmentConfig (domyślna, DEBUG=True)
    testing      → TestingConfig     (SQLite :memory:, bez CSRF)
    production   → ProductionConfig  (PostgreSQL, DEBUG=False)

Lokalnie: brak FLASK_CONFIG → używany "default" → DevelopmentConfig.
Railway:  FLASK_CONFIG=production → ProductionConfig.

FLASK_ENV jest deprecated od Flask 2.3 i usunięte w Flask 2.3+.
Źródło: https://flask.palletsprojects.com/en/stable/changes/
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Wczytaj .env z katalogu głównego projektu PRZED importem aplikacji.
# Path(__file__).resolve().parent → katalog gdzie leży run.py = katalog główny.
# Jeśli .env nie istnieje – load_dotenv() nie robi nic, bez błędu.
load_dotenv(Path(__file__).resolve().parent / ".env")

# Import po load_dotenv() – config.py może teraz odczytać zmienne środowiskowe
from app import create_app  # noqa: E402

# FLASK_CONFIG wybiera środowisko:
#   lokalnie: brak zmiennej → "default" → DevelopmentConfig
#   Railway:  FLASK_CONFIG=production → ProductionConfig
config_name = os.environ.get("FLASK_CONFIG", "default")
app = create_app(config_name)

if __name__ == "__main__":
    # app.run() używa ustawień z DevelopmentConfig (DEBUG=True).
    # Flask domyślnie uruchamia serwer na http://127.0.0.1:5000
    # Na produkcji aplikację uruchamia gunicorn (Procfile), nie ten blok.
    app.run()
