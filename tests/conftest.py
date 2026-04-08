"""
Fixtures współdzielone przez wszystkie testy.

Dokumentacja pytest fixtures:
    https://docs.pytest.org/en/stable/reference/fixtures.html

Dokumentacja testowania Flask:
    https://flask.palletsprojects.com/en/stable/testing/

Hierarchia fixtures w tym pliku:
    app          → instancja aplikacji (raz na sesję)
    db           → czysta baza przed każdym testem (function scope)
    client       → test client HTTP (zależy od db)
    user         → użytkownik testowy w bazie (zależy od db)
    logged_in_client → client z zalogowanym userem (zależy od client i user)

Dlaczego scope="session" dla app?
    Tworzenie aplikacji Flask jest kosztowne – inicjalizacja extensions,
    rejestracja blueprintów, filtrów Jinja2. Robimy to raz na całą sesję.

Dlaczego scope="function" dla db?
    Każdy test musi startować z czystą bazą – bez danych z poprzedniego testu.
    create_all() + drop_all() wokół każdego testu gwarantuje izolację.

Dlaczego WTF_CSRF_ENABLED=False w TestingConfig?
    Testy POST nie generują tokenów CSRF – wyłączenie upraszcza testowanie
    formularzy bez konieczności wyciągania tokenu z każdego GET.
"""
import pytest
from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture(scope="session")
def app():
    """
    Instancja aplikacji Flask skonfigurowana do testów.

    scope="session" – tworzona raz dla całej sesji testów.
    TestingConfig używa SQLite :memory: i wyłącza CSRF.
    """
    application = create_app("testing")
    return application


@pytest.fixture(scope="function")
def db(app):
    """
    Czysta baza danych przed każdym testem.

    scope="function" – każdy test dostaje świeże, puste tabele.
    yield oddziela setup (przed testem) od teardown (po teście):
        - przed: create_all() tworzy wszystkie tabele
        - po:    session.remove() + drop_all() usuwa wszystko

    Dzięki temu testy są izolowane – dane z jednego testu
    nie wpływają na kolejny.
    """
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app, db):
    """
    Test client Flask – wysyła HTTP requesty bez uruchamiania serwera.

    Zależy od db – gwarantuje że tabele istnieją przed wysłaniem requestu.
    WTF_CSRF_ENABLED=False w TestingConfig – POST nie wymaga tokenu CSRF.
    """
    return app.test_client()


@pytest.fixture(scope="function")
def user(db):
    """
    Gotowy użytkownik testowy w bazie.

    Używany przez testy wymagające istniejącego konta (np. logowanie,
    edycja profilu, operacje portfelowe).

    Dane:
        username:    testuser
        email:       test@example.com
        password:    password123  (zahashowane w bazie)
        balance_usd: 10 000.00
    """
    u = User(
        username="testuser",
        email="test@example.com",
        password_hash=generate_password_hash("password123"),
        balance_usd=10_000.0,
    )
    _db.session.add(u)
    _db.session.commit()
    return u


@pytest.fixture(scope="function")
def logged_in_client(client, user):
    """
    Test client z zalogowanym użytkownikiem testowym.

    Używany przez testy endpointów chronionych @login_required.
    Loguje się przez normalny endpoint POST /auth/login – tak samo
    jak prawdziwy użytkownik.
    """
    client.post("/auth/login", data={
        "username": "testuser",
        "password": "password123",
    }, follow_redirects=True)
    return client

