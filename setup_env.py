"""
Konfiguracja środowiska aplikacji Crypto Monitor.

Tworzy plik .env z automatycznie wygenerowanym SECRET_KEY
i opcjonalnym kluczem API CoinGecko.

Użycie:
    python setup_env.py

Przeznaczony do uruchomienia w łańcuchu komend po pip install:
    git clone ... && cd ... && ... && python setup_env.py && flask --app run db upgrade && python run.py

SECRET_KEY generowany jest automatycznie przez secrets.token_hex(32)
z kryptograficznie bezpiecznego źródła (os.urandom).
Źródło: https://docs.python.org/3/library/secrets.html

Plik .env jest wykluczony z repozytorium przez .gitignore.
Wzorzec zgodny z metodyką 12-Factor App: https://12factor.net/config
"""
import secrets
import sys
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent / ".env"


def main():
    if ENV_PATH.exists():
        print(f"\n  .env już istnieje — pomijam konfigurację.\n")
        sys.exit(0)

    secret_key = secrets.token_hex(32)

    print()
    print("=" * 55)
    print("  Crypto Monitor — konfiguracja")
    print("=" * 55)
    print()
    print(f"  SECRET_KEY wygenerowany automatycznie.")
    print()
    print("  COINGECKO_API_KEY — klucz do pobierania danych")
    print("  o kryptowalutach. Bez niego aplikacja działa,")
    print("  ale limit zapytań jest niestabilny (~5-15 req/min).")
    print("  Darmowy klucz: https://www.coingecko.com/pl/api/pricing")
    print()

    while True:
        answer = input("  Masz klucz API CoinGecko? [y/n]: ").strip().lower()
        if answer in ("y", "n"):
            break
        print("  Wpisz 'y' lub 'n'.")

    api_key = ""
    if answer == "y":
        api_key = input("  Wklej klucz: ").strip()
        if api_key:
            print("  Klucz zapisany.")
        else:
            print("  Pusty klucz — pominięto.")
    else:
        print("  Pominięto — uzupełnij później w pliku .env.")

    ENV_PATH.write_text(
        "# Wygenerowano przez setup_env.py\n"
        f"SECRET_KEY={secret_key}\n"
        f"COINGECKO_API_KEY={api_key}\n"
    )

    print()
    print(f"  .env zapisany.")
    print("=" * 55)
    print()


if __name__ == "__main__":
    main()
