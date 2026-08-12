"""
SQLAlchemy engine and database session setup.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    sessionmaker,
)

from app.config import get_settings


# ============================================================
# CONFIG
# ============================================================

settings = get_settings()


# ============================================================
# ENGINE
# ============================================================

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)


# ============================================================
# SESSION
# ============================================================

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ============================================================
# BASE MODEL
# ============================================================

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    """

    pass


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db() -> Generator[Session, None, None]:
    """
    Provide a database session to FastAPI endpoints.

    The session is always closed after the request finishes.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()