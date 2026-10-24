"""Database declarative base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.x DeclarativeBase for all ORM models."""
