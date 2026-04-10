# Crypto Monitor

Webowa aplikacja do monitorowania kryptowalut i symulacji handlu.  
Zbudowana w Pythonie (Flask + SQLAlchemy) jako projekt edukacyjny.

## Funkcje

- monitorowanie aktualnych cen kryptowalut (CoinGecko API)
- historia cen z wykresem i zakresami 24h / 7d / 30d
- rejestracja i logowanie użytkowników
- własny portfel z wirtualnym saldem startowym $10 000 USD
- symulacja kupna i sprzedaży kryptowalut
- historia transakcji z obliczeniem zysku / straty (P&L)
- pobieranie historii transakcji do pliku CSV
- czyszczenie historii cen kryptowalut starszych niż 30 dni
- usuwanie konta użytkownika
- aplikacja zawiera testy

## Wymagania

- Python 3.12+
- klucz API CoinGecko (darmowy plan Demo) — opcjonalny do uruchomienia aplikacji lokalnie
- Skrypt `setup_env.py` wygeneruje `SECRET_KEY` automatycznie i zapyta o klucz API CoinGecko. Klucz API można
  pominąć (n) — aplikacja uruchomi się z niestabilnym limitem zapytań. Historia cen kryptowalut również może nie być
  stabilna, co może mieć odzwierciedlenie na wykresie kryptowaluty. Po odpowiedzi reszta komend wykona się automatycznie.
- na produkcji (Railway): PostgreSQL — konfiguracja automatyczna przez zmienne środowiskowe

## Uruchomienie

- aplikacja dostępna jest w dwóch wariantach do uruchomienia: na serwerze zewnętrznym Railway i lokalnie
- uruchomienie aplikacji na serwerze zewnętrznym Railway: przy pierwszym wejściu prawdopodobnie wystąpi cold start
  (~15s) pod adresem: https://web-production-b2975.up.railway.app/coins/
- poniżej przykład uruchomienia i przetestowania aplikacji lokalnie:

### Linux / Mac

```bash
git clone https://gitlab.com/argrntar/cryptomonitor.git
cd cryptomonitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python setup_env.py
flask --app run db upgrade
python run.py
```

### Windows

```cmd
git clone https://gitlab.com/argrntar/cryptomonitor.git
cd cryptomonitor
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python setup_env.py
flask --app run db upgrade
python run.py
```

- lokalnie aplikacja dostępna pod: **http://127.0.0.1:5000**

---

## Jak uzyskać klucz API CoinGecko

Aplikacja pobiera dane o kryptowalutach z API CoinGecko.
Darmowy plan Demo zapewnia stabilny limit 30 zapytań/min
i miesięczny limit 10 000 zapytań — w zupełności wystarczający
do korzystania z aplikacji lokalnie.

### Krok po kroku

1. Wejdź na stronę: https://www.coingecko.com/pl/api/pricing
2. Zarejestruj nowe konto CoinGecko lub zaloguj się na istniejące
   - do rejestracji potrzebujesz tylko adres e-mail
   - nie jest wymagana karta płatnicza
3. Po zalogowaniu przejdź do: https://docs.coingecko.com/docs/setting-up-your-api-key
4. Kliknij przycisk: https://www.coingecko.com/en/developers/dashboard
5. Skopiuj wygenerowany klucz API
6. Wklej go do pliku `.env` jako wartość `COINGECKO_API_KEY`
   lub podaj go podczas uruchamiania `python setup_env.py`

```
COINGECKO_API_KEY=CG-xxxxxxxxxxxxxxxxxxxx
```

### Co jeśli nie ustawię klucza?

Aplikacja uruchomi się i będzie działać, ale bez klucza API
limit zapytań jest niestabilny (~5–15 req/min) i może powodować
błędy przy pobieraniu danych. W terminalu pojawi się ostrzeżenie
z instrukcją co zrobić.

---

## SECRET_KEY

`SECRET_KEY` to tajny klucz używany przez Flask do podpisywania
sesji użytkowników i tokenów CSRF. Skrypt `setup_env.py`
generuje go automatycznie przy pierwszym uruchomieniu.

Jeśli chcesz wygenerować go ręcznie:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Domyślna wartość `dev-secret-key-change-in-production` jest
zakodowana w `config.py` i pozwala uruchomić aplikację bez `.env`.
Jednak ten sam klucz ma każdy kto sklonuje repozytorium — sesje
użytkowników mogłyby zostać sfałszowane. Własny losowy klucz
eliminuje to ryzyko.

---

## Testy

Projekt zawiera testy jednostkowe i funkcjonalne napisane w pytest.

```bash
# Uruchom wszystkie testy - szczegółowy widok
pytest -v
```

```bash
# Z pokryciem kodu
pytest --cov=app --cov-report=term-missing
```

### Struktura testów

```
tests/
├── conftest.py                      # fixtures: app, db, client, user, logged_in_client
├── unit/
│   ├── test_auth_service.py         # register, authenticate, update_profile, delete_account
│   ├── test_portfolio_service.py    # buy, sell, build_positions, get_min_sell_amount
│   └── test_coin_service.py         # update_prices, ensure_history, cleanup_coin_history
└── functional/
    ├── test_auth_routes.py          # rejestracja, logowanie, profil, usunięcie konta
    ├── test_coin_routes.py          # lista monet, szczegóły, historia AJAX
    ├── test_trade_routes.py         # formularz, kupno, sprzedaż
    └── test_portfolio_routes.py     # dashboard, historia, CSV, zamknij wszystko
```

Testy używają bazy SQLite `:memory:` – izolowanej, tworzonej i usuwanej przy każdym teście.

---

## Struktura projektu

```
cryptomonitor/
│
├── run.py                      # punkt wejścia — uruchamia aplikację
├── setup_env.py                # interaktywna konfiguracja .env
├── requirements.txt            # zależności Python
├── pytest.ini                  # konfiguracja pytest
├── README.md                   # dokumentacja projektu
├── Procfile                    # konfiguracja startu aplikacji na Railway
├── .env.example                # szablon konfiguracji (dokumentacja zmiennych)
├── .gitignore                  # pliki wykluczone z repozytorium
│
├── migrations/                 # migracje bazy danych (Alembic)
│   ├── env.py
│   └── versions/               # pliki migracji (historia schematu)
│
├── data/                       # ⛔ NIE w repo (.gitignore)
│   └── cryptomonitor.db        # baza SQLite (tworzona przez flask db upgrade)
│
├── tests/                      # testy jednostkowe i funkcjonalne
│   ├── conftest.py             # fixtures współdzielone
│   ├── unit/                   # testy serwisów (bez HTTP)
│   └── functional/             # testy endpointów HTTP
│
└── app/                        # pakiet aplikacji Flask
    ├── __init__.py             # fabryka aplikacji — create_app()
    ├── config.py               # konfiguracja środowisk (dev/test/prod)
    ├── extensions.py           # instancje db, migrate, login_manager
    ├── exceptions.py           # własne klasy wyjątków domenowych
    │
    ├── models/                 # modele SQLAlchemy (tabele bazy danych)
    │   ├── user.py             # User – konto, saldo, relacje
    │   ├── coin.py             # Coin – moneta, cena, market cap
    │   ├── price_history.py    # PriceHistory – historia cen (indeks kompozytowy)
    │   ├── portfolio.py        # Portfolio – pozycje portfelowe użytkownika
    │   └── transaction.py      # Transaction – historia kupna/sprzedaży
    │
    ├── repositories/           # dostęp do bazy (tylko SQL, zero logiki)
    │   ├── coin_repository.py
    │   ├── price_history_repository.py
    │   ├── portfolio_repository.py
    │   ├── transaction_repository.py
    │   └── user_repository.py
    │
    ├── services/               # logika biznesowa
    │   ├── coin_service.py     # ceny, historia, throttling CoinGecko
    │   ├── portfolio_service.py # kupno, sprzedaż, P&L, agregacja danych
    │   └── auth_service.py     # rejestracja, logowanie, profil, usunięcie konta
    │
    ├── api_clients/            # komunikacja z zewnętrznymi API
    │   └── coingecko_client.py # pobieranie cen i historii z CoinGecko
    │
    ├── forms/                  # formularze WTForms
    │   ├── auth_forms.py       # RegisterForm, LoginForm, EditProfileForm
    │   └── trade_forms.py      # BuyForm, SellForm (FlexibleDecimalField)
    │
    ├── routes/                 # endpointy HTTP (blueprinty Flask)
    │   ├── main_routes.py      # root redirect (/)
    │   ├── auth_routes.py      # rejestracja, logowanie, profil, usunięcie konta
    │   ├── coin_routes.py      # lista monet, szczegóły, historia AJAX
    │   ├── trade_routes.py     # kupno i sprzedaż
    │   └── portfolio_routes.py # portfel, historia, eksport CSV
    │
    ├── templates/              # szablony Jinja2 (HTML)
    │   ├── base.html           # layout, nawigacja, flash messages
    │   ├── auth/               # rejestracja, logowanie, profil
    │   ├── coins/              # lista monet, szczegóły z wykresem
    │   ├── portfolio/          # dashboard, historia transakcji
    │   └── trade/              # formularz kupna/sprzedaży
    │
    └── static/                 # pliki statyczne
        ├── css/style.css       # dark theme, komponenty UI
        └── js/
            ├── price_chart.js  # wykres Chart.js z cache i filtrowaniem
            ├── dashboard.js    # obsługa modalu "Zamknij wszystko"
            ├── trade.js        # podgląd kosztu przy kupnie/sprzedaży
            └── profile.js      # obsługa modalu usunięcia konta
```

---

## Deployment (Railway)

Aplikacja skonfigurowana do deploymentu na [Railway](https://railway.app).

### Wymagane zmienne środowiskowe (ustawiane w panelu Railway)

| Zmienna | Opis |
|---|---|
| `SECRET_KEY` | Losowy klucz — wygeneruj: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Automatycznie ustawiana przez Railway po dodaniu PostgreSQL (`${{Postgres.DATABASE_URL}}`) |
| `COINGECKO_API_KEY` | Opcjonalny klucz API CoinGecko |
| `FLASK_CONFIG` | Ustaw na `production` — wybiera ProductionConfig z config.py |

### Uruchomienie na Railway

Railway automatycznie:
1. Instaluje zależności z `requirements.txt`
2. Wykonuje `flask db upgrade` (migracje na PostgreSQL) na podstawie `Procfile`
3. Uruchamia `gunicorn "run:app"` (na podstawie `Procfile`)

### Uwaga — psycopg2-binary

Jeśli chcesz testować PostgreSQL lokalnie:
```bash
pip install psycopg2-binary
```

---

## Technologie

| Technologia       | Wersja   | Zastosowanie                                               |
|-------------------|----------|------------------------------------------------------------|
| Flask             | 3.1.x    | framework webowy, blueprinty, Jinja2                       |
| SQLAlchemy        | 2.0.x    | ORM, zapytania, unit of work, identity map                 |
| Flask-SQLAlchemy  | 3.1.x    | integracja SQLAlchemy z Flask                              |
| Flask-Migrate     | 4.1.x    | migracje schematu bazy danych (Alembic)                    |
| Flask-Login       | 0.6.x    | sesje użytkowników, @login_required, user_loader           |
| Flask-WTF         | 1.2.x    | formularze z ochroną CSRF                                  |
| Flask-Talisman    | 1.1.x    | nagłówki bezpieczeństwa HTTP (CSP, HSTS, clickjacking)     |
| WTForms           | 3.2.x    | walidacja pól, FlexibleDecimalField (przecinek/kropka)     |
| email-validator   | 2.x      | walidacja adresów email w formularzach                     |
| python-dotenv     | 1.x      | zmienne środowiskowe z pliku .env                          |
| httpx             | 0.28.x   | klient HTTP do komunikacji z CoinGecko API                 |
| Chart.js          | 4.4.0    | interaktywny wykres historii cen (CDN)                     |
| SQLite            | —        | baza danych lokalnie (dev/test)                            |
| PostgreSQL        | —        | baza danych na produkcji (Railway)                         |
| gunicorn          | 21.2.x   | serwer WSGI na produkcji (Railway)                         |
| psycopg2-binary   | 2.9.x    | driver PostgreSQL (instalowany tylko na Railway)           |
| pytest            | 9.x      | testy jednostkowe i funkcjonalne                           |
