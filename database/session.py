"""Conexión a la base de datos.

Orden de resolución de la URL:
  1. st.secrets["database"]["url"]
  2. variable de entorno DATABASE_URL
  3. sqlite:///data/insurance_leads.db  (solo desarrollo local / demo)

Producción: usa PostgreSQL administrado (Neon, Supabase, RDS, Cloud SQL…):
    [database]
    url = "postgresql+psycopg2://usuario:clave@host:5432/insurance_leads?sslmode=require"
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base
from utils.config import get_secret

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "insurance_leads.db"

_ENGINES: dict[str, Engine] = {}
_MAKERS: dict[str, sessionmaker] = {}


def get_database_url() -> str:
    url = get_secret("url", section="database") or os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        return url
    DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE_PATH}"


def is_sqlite(url: Optional[str] = None) -> bool:
    return (url or get_database_url()).startswith("sqlite")


def get_engine(url: Optional[str] = None) -> Engine:
    url = url or get_database_url()
    if url not in _ENGINES:
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(engine, "connect")
            def _pragmas(dbapi_conn, _record):  # pragma: no cover
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        Base.metadata.create_all(engine)
        from database.migrations import run_migrations
        run_migrations(engine)
        _ENGINES[url] = engine
        _MAKERS[url] = sessionmaker(bind=engine, expire_on_commit=False)
    return _ENGINES[url]


def init_db(url: Optional[str] = None) -> Engine:
    return get_engine(url)


@contextmanager
def session_scope(url: Optional[str] = None) -> Iterator[Session]:
    url = url or get_database_url()
    get_engine(url)
    session: Session = _MAKERS[url]()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def masked_url(url: Optional[str] = None) -> str:
    url = url or get_database_url()
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        return f"{scheme}://{creds.split(':', 1)[0]}:****@{host}"
    return url
