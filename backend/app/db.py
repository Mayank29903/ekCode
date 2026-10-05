from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def contains(q: str) -> str:
    """ILIKE pattern for a user-typed substring; % and _ are matched literally (use with escape='\\')."""
    return "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
