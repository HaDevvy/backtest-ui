"""Database access. The UI only reads; it never creates or alters tables."""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_url = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://backtest:backtest@localhost:5432/backtest",
)
# Accept a plain postgresql:// URL and use the psycopg 3 driver for it.
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
