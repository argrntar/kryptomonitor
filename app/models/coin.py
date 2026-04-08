"""
Model monety kryptowalutowej.

Relacje zdefiniowane przez back_populates (obie strony jawnie):
    price_history     – historia cen (PriceHistory)
    portfolio_entries – pozycje portfelowe użytkowników (Portfolio)
    transactions      – transakcje kupna/sprzedaży (Transaction)

back_populates vs backref:
    backref automatycznie tworzy odwrotną relację na drugim modelu –
    "magia w tle", trudna do śledzenia i typowania.
    back_populates wymaga jawnej deklaracji na obu modelach –
    czytelniejsze, wymagane przez SQLAlchemy 2.0 typed API (Mapped[]).
    Dokumentacja: https://docs.sqlalchemy.org/en/20/orm/relationship_api.html
"""
from app.extensions import db


class Coin(db.Model):
    __tablename__ = "coins"

    id = db.Column(db.Integer, primary_key=True)
    coingecko_id = db.Column(db.String(64), unique=True, nullable=False)
    # unique=True automatycznie tworzy indeks B-tree na coingecko_id
    symbol = db.Column(db.String(16), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    current_price_usd = db.Column(db.Float, nullable=True)
    market_cap = db.Column(db.Float, nullable=True)
    price_change_24h = db.Column(db.Float, nullable=True)
    last_updated = db.Column(db.DateTime, nullable=True)

    # Relacje – back_populates zamiast backref
    # lazy="select" (domyślne) – ładuje powiązane rekordy przy pierwszym dostępie
    # cascade="all, delete-orphan" – usuwa historię/transakcje gdy moneta usunięta
    price_history = db.relationship(
        "PriceHistory",
        back_populates="coin",
        lazy="select",
        cascade="all, delete-orphan",
    )
    portfolio_entries = db.relationship(
        "Portfolio",
        back_populates="coin",
        lazy="select",
        cascade="all, delete-orphan",
    )
    transactions = db.relationship(
        "Transaction",
        back_populates="coin",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Coin {self.symbol} ${self.current_price_usd}>"
