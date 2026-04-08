"""
Model transakcji kupna lub sprzedaży kryptowaluty.

Indeks (user_id, created_at):
    Composite index pokrywa wszystkie zapytania w transaction_repository:

        find_recent_by_user(user_id):
            WHERE user_id = ? ORDER BY created_at DESC LIMIT 10
            → indeks używany w pełni

        find_all_by_user(user_id):
            WHERE user_id = ? ORDER BY created_at DESC
            → indeks używany w pełni

        find_by_user_paginated(user_id, page):
            WHERE user_id = ? ORDER BY created_at DESC
            → indeks używany w pełni

        count_by_user(user_id):
            SELECT count(*) WHERE user_id = ?
            → indeks pokrywa filtr (index-only scan możliwy)

    Bez indeksu każde zapytanie = full table scan. Przy 100 userach
    × 1000 transakcji = 100 000 wierszy skanowanych przy każdym
    wejściu na dashboard.

transaction_type przechowywany jako String(4) – "buy" lub "sell".
    Enum byłby bezpieczniejszy typowo ale String(4) jest prostszy
    w migracji i kompatybilny ze wszystkimi bazami danych.
"""
from datetime import datetime, timezone

from app.extensions import db


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    coin_id = db.Column(db.Integer, db.ForeignKey("coins.id"), nullable=False)
    transaction_type = db.Column(db.String(4), nullable=False)  # "buy" | "sell"
    amount = db.Column(db.Float, nullable=False)
    price_usd = db.Column(db.Float, nullable=False)
    total_usd = db.Column(db.Float, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Composite index – pokrywa wszystkie zapytania transaction_repository
    # Kolejność: user_id pierwsza (filtr equality), created_at druga (sort/range)
    __table_args__ = (
        db.Index("ix_transaction_user_created", "user_id", "created_at"),
    )

    # Strony odwrotne relacji zdefiniowanych w User i Coin
    user = db.relationship("User", back_populates="transactions")
    coin = db.relationship("Coin", back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction {self.transaction_type} "
            f"{self.amount} coin_id={self.coin_id}>"
        )
