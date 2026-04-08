"""
Model użytkownika aplikacji.

Relacje zdefiniowane przez back_populates (obie strony jawnie).

lazy="select" zamiast lazy="dynamic":
    lazy="dynamic" był przestarzały już od SQLAlchemy 1.4 i usunięty
    w SQLAlchemy 2.0. Zwracał obiekt Query zamiast listy – wymagał
    dodatkowego .all() przy każdym użyciu i nie działał z async.
    lazy="select" (domyślne) ładuje relację jako listę przy pierwszym
    dostępie do atrybutu.

    Dokumentacja: https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html
    "The 'dynamic' loader is legacy as of SQLAlchemy 2.0."

Uwaga: relacje portfolio i transactions nie są bezpośrednio używane
    w kodzie aplikacji (dostęp przez repozytoria). Są zdefiniowane dla:
    - cascade="all, delete-orphan" – spójna obsługa usuwania usera
    - Alembic – widzi kompletny schemat relacji
"""
from datetime import datetime, timezone

from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    # index=True na username i email – często szukane w find_by_username/email
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    balance_usd = db.Column(db.Float, nullable=False, default=10_000.0)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # lazy="select" zamiast deprecated lazy="dynamic"
    portfolio = db.relationship(
        "Portfolio",
        back_populates="user",
        lazy="select",
        cascade="all, delete-orphan",
    )
    transactions = db.relationship(
        "Transaction",
        back_populates="user",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"
