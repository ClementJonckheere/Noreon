"""Session SQLAlchemy vers la base interne de Noreon."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """Dépendance FastAPI : ouvre/ferme une session par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
