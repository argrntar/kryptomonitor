"""
Repozytorium dla tabeli users.

Odpowiedzialności:
    - pobieranie użytkownika po id, username, email
    - sprawdzanie unikalności username i email (dla walidatorów formularzy)
    - tworzenie nowego użytkownika (INSERT z flush – commit w serwisie)

Nie odpowiada za:
    - hashowanie haseł – auth_service
    - logikę rejestracji / logowania – auth_service
    - commit transakcji – auth_service

Konwencja:
    Tylko module-level functions – bez klas opakowujących.
    Klasa UserRepository była wzorcem Java/Spring niepotrzebnym w Pythonie
    gdzie moduł sam w sobie jest singletonem (importowany raz).

Konwencja flush vs commit:
    create() używa flush() – obiekt dostaje id ale transakcja NIE jest
    zatwierdzona. Commit należy do serwisu (auth_service.register).

Używane przez:
    - auth_service.py   (register, authenticate, update_profile)
    - auth_forms.py     (validate_username, validate_email – sprawdzanie unikalności)
"""
from sqlalchemy import select
from decimal import Decimal
from app.extensions import db
from app.models.user import User


def find_by_id(user_id: int) -> User | None:
    """
    Zwraca użytkownika po kluczu głównym.

    Używa db.session.get() – korzysta z identity map sesji SQLAlchemy,
    brak dodatkowego SELECT jeśli obiekt jest już w pamięci sesji.

    Args:
        user_id: Klucz główny użytkownika.

    Returns:
        Obiekt User lub None jeśli nie istnieje.
    """
    return db.session.get(User, user_id)


def find_by_username(username: str) -> User | None:
    """
    Zwraca użytkownika po nazwie użytkownika.

    Args:
        username: Nazwa użytkownika (case-sensitive).

    Returns:
        Obiekt User lub None jeśli nie istnieje.
    """
    stmt = select(User).filter_by(username=username)
    return db.session.execute(stmt).scalar_one_or_none()


def find_by_email(email: str) -> User | None:
    """
    Zwraca użytkownika po adresie email.

    Args:
        email: Adres email.

    Returns:
        Obiekt User lub None jeśli nie istnieje.
    """
    stmt = select(User).filter_by(email=email)
    return db.session.execute(stmt).scalar_one_or_none()


def username_exists(username: str) -> bool:
    """
    Sprawdza czy nazwa użytkownika jest już zajęta.

    Używana przez walidatory w RegisterForm i EditProfileForm.

    Args:
        username: Nazwa do sprawdzenia.

    Returns:
        True jeśli zajęta, False jeśli dostępna.
    """
    return find_by_username(username) is not None


def email_exists(email: str) -> bool:
    """
    Sprawdza czy adres email jest już zarejestrowany.

    Używana przez walidatory w RegisterForm i EditProfileForm.

    Args:
        email: Adres email do sprawdzenia.

    Returns:
        True jeśli zajęty, False jeśli dostępny.
    """
    return find_by_email(email) is not None


def create(
        username: str,
        email: str,
        password_hash: str,
        balance_usd: Decimal = Decimal("10000.00"),
) -> User:
    """
    Tworzy nowego użytkownika i zwraca obiekt z wypełnionym id.

    Używa flush() – obiekt dostaje id z bazy ale transakcja NIE jest
    zatwierdzona. Commit należy do auth_service.register().

    Args:
        username:      Unikalna nazwa użytkownika.
        email:         Unikalny adres email.
        password_hash: Hash hasła (werkzeug generate_password_hash).
        balance_usd:   Startowe saldo w USD (domyślnie $10 000).

    Returns:
        Nowy obiekt User z id – niezatwierdzony w bazie.
    """
    user = User(
        username=username,
        email=email,
        password_hash=password_hash,
        balance_usd=balance_usd,
    )
    db.session.add(user)
    db.session.flush()  # id dostępne, commit w auth_service
    return user
