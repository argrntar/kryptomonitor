"""
Serwis autoryzacji i zarządzania kontem użytkownika.

Odpowiedzialności:
    - rejestracja nowego użytkownika (deleguje zapis do user_repository)
    - weryfikacja danych logowania
    - aktualizacja profilu (dane + opcjonalna zmiana hasła)

Nie odpowiada za:
    - zapytania SQL – user_repository
    - renderowanie HTML / flash messages – auth_routes
    - hashowanie haseł to szczegół implementacyjny serwisu (werkzeug.security)

Konwencja:
    Tylko module-level functions – bez klasy AuthService.
    Klasa była wzorcem Java/Spring niepotrzebnym w Pythonie
    gdzie moduł jest singletonem. Reszta aplikacji używa tego samego
    wzorca (coin_service, portfolio_service).

Konwencja commit:
    register() – commit po create() w user_repository (rejestracja jest atomowa)
    update_profile() – commit bezpośrednio (user jest już śledzony przez sesję
                       Flask-Login, nie trzeba go ponownie dodawać przez repo)
"""
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.models.user import User
from app.repositories import user_repository
from app.repositories import portfolio_repository
from app.repositories import coin_repository


def register(username: str, email: str, password: str) -> User:
    """
    Tworzy nowego użytkownika z hashowanym hasłem i startowym saldem.

    Zakłada że walidacja unikalności username i email odbyła się
    w walidatorach formularza (RegisterForm.validate_username/email).
    Deleguje tworzenie rekordu do user_repository.create() (flush),
    następnie commituje.

    Args:
        username: Unikalna nazwa użytkownika.
        email:    Unikalny adres email.
        password: Hasło w plain text – zostanie zahashowane.

    Returns:
        Zapisany obiekt User z saldem $10 000 i id z bazy.
    """
    user = user_repository.create(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.commit()
    return user


def authenticate(username: str, password: str) -> User | None:
    """
    Weryfikuje dane logowania.

    Używa check_password_hash – porównanie hash vs plain text
    jest bezpieczne na timing attacks dzięki werkzeug.

    Args:
        username: Nazwa użytkownika.
        password: Hasło w plain text.

    Returns:
        Obiekt User jeśli dane poprawne, None jeśli nie.
    """
    user = user_repository.find_by_username(username)
    if user is None:
        return None
    if not check_password_hash(user.password_hash, password):
        return None
    return user


def update_profile(
        user: User,
        username: str,
        email: str,
        current_password: str = "",
        new_password: str = "",
) -> tuple[bool, str]:
    """
    Aktualizuje dane profilu użytkownika.

    Zmiana hasła jest opcjonalna – odbywa się tylko gdy new_password
    jest niepusty. W takim przypadku current_password musi być poprawny.

    Nie woła user_repository – obiekt user jest już śledzony przez
    sesję SQLAlchemy (załadowany przez Flask-Login user_loader przy każdym
    requeście). Wystarczy zmodyfikować atrybuty i commitować.

    Args:
        user:             Zalogowany użytkownik do aktualizacji.
        username:         Nowa nazwa użytkownika.
        email:            Nowy adres email.
        current_password: Aktualne hasło (wymagane przy zmianie).
        new_password:     Nowe hasło (opcjonalne – pusty string = brak zmiany).

    Returns:
        Tuple (success: bool, message: str).
    """
    if new_password:
        if not check_password_hash(user.password_hash, current_password):
            return False, "Aktualne hasło jest nieprawidłowe."
        user.password_hash = generate_password_hash(new_password)

    user.username = username
    user.email = email
    db.session.commit()
    return True, "Profil został zaktualizowany."


def delete_account(user: User, password: str) -> tuple[bool, str]:
    """
    Usuwa konto użytkownika wraz ze wszystkimi powiązanymi danymi.

    Walidacja (w kolejności):
        1. Weryfikacja hasła – zabezpieczenie przed przypadkowym/złośliwym usunięciem
        2. Brak otwartych pozycji – user musi najpierw sprzedać wszystkie kryptowaluty
           przez "Zamknij wszystko" w portfelu

    Cascade delete zdefiniowany w modelu User usuwa automatycznie:
        - Portfolio (pozycje portfelowe, wszystkie z amount == 0)
        - Transaction (pełna historia transakcji)

    Operacja jest nieodwracalna.

    Args:
        user:     Zalogowany użytkownik do usunięcia.
        password: Hasło w plain text – weryfikacja tożsamości.

    Returns:
        Tuple (success: bool, message: str).
    """
    if not check_password_hash(user.password_hash, password):
        return False, "Nieprawidłowe hasło. Konto nie zostało usunięte."

    # Sprawdź czy user ma otwarte pozycje (amount > 0)
    holdings = portfolio_repository.find_by_user(user.id)
    open_positions = [h for h in holdings if h.amount > 0]

    if open_positions:
        coin_ids = [h.coin_id for h in open_positions]
        coins = coin_repository.find_by_ids(coin_ids)
        coins_map = {c.id: c for c in coins}
        symbols = ", ".join(
            coins_map[h.coin_id].symbol if h.coin_id in coins_map else "?"
            for h in open_positions
        )
        count = len(open_positions)
        return (
            False,
            f"Masz {count} otwart{'ą pozycję' if count == 1 else 'e pozycje'} "
            f"w portfelu ({symbols}). "
            f"Przed usunięciem konta sprzedaj wszystkie kryptowaluty – "
            f"użyj przycisku 'Zamknij wszystko' w portfelu."
        )

    db.session.delete(user)
    db.session.commit()
    return True, "Konto zostało trwale usunięte."
