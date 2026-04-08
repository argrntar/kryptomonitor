"""
Model pozycji portfelowej użytkownika.

Jeden rekord = jedna pozycja (user, coin) z bieżącą ilością i
średnią ceną zakupu (weighted average).

Indeksowanie:
    UniqueConstraint(user_id, coin_id) automatycznie tworzy composite
    index B-tree na (user_id, coin_id). Pokrywa:
        find_by_user(user_id)            → WHERE user_id = ?
        find_by_user_and_coin(uid, cid)  → WHERE user_id = ? AND coin_id = ?
    Baza danych może użyć leftmost prefix composite indexu do zapytań
    filtrujących tylko po user_id – dodatkowy osobny indeks zbędny.

    Dokumentacja: https://docs.sqlalchemy.org/en/20/core/constraints.html
"""
from datetime import datetime, timezone

from app.extensions import db


class Portfolio(db.Model):
    __tablename__ = "portfolio"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    coin_id = db.Column(db.Integer, db.ForeignKey("coins.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    avg_buy_price = db.Column(db.Float, nullable=False, default=0.0)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # UniqueConstraint tworzy composite index (user_id, coin_id) automatycznie
    __table_args__ = (
        db.UniqueConstraint("user_id", "coin_id", name="uq_portfolio_user_coin"),
    )

    # Strony odwrotne relacji zdefiniowanych w User i Coin
    user = db.relationship("User", back_populates="portfolio")
    coin = db.relationship("Coin", back_populates="portfolio_entries")

    def __repr__(self) -> str:
        return (
            f"<Portfolio user_id={self.user_id} "
            f"coin_id={self.coin_id} amount={self.amount}>"
        )
