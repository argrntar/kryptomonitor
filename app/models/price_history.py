"""
Model punktu historii ceny kryptowaluty.

Indeks (coin_id, recorded_at):
    Composite index pokrywa wszystkie zapytania w price_history_repository:

        find_since(coin_id, since):
            WHERE coin_id = ? AND recorded_at >= ?
            → indeks używany w pełni (oba pola)

        find_oldest_by_coin_id(coin_id):
            WHERE coin_id = ? ORDER BY recorded_at ASC LIMIT 1
            → indeks używany w pełni (coin_id filtr + recorded_at sort)

    Bez indeksu każde zapytanie = full table scan na potencjalnie
    dziesiątkach tysięcy wierszy (20 monet × 288 punktów/dobę × 30 dni
    = ~172 800 wierszy).

    Dokumentacja: https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.Index
"""
from datetime import datetime, timezone

from app.extensions import db


class PriceHistory(db.Model):
    __tablename__ = "price_history"

    id = db.Column(db.Integer, primary_key=True)
    coin_id = db.Column(db.Integer, db.ForeignKey("coins.id"), nullable=False)
    price_usd = db.Column(db.Numeric(18, 8), nullable=False)
    recorded_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Composite index – pokrywa find_since() i find_oldest_by_coin_id()
    # Kolejność kolumn: coin_id pierwsza (filtr equality), recorded_at druga (range/sort)
    __table_args__ = (
        db.Index("ix_price_history_coin_recorded", "coin_id", "recorded_at"),
    )

    # Strona odwrotna relacji zdefiniowanej w Coin.price_history
    coin = db.relationship("Coin", back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory coin_id={self.coin_id} price_usd={self.price_usd}>"
