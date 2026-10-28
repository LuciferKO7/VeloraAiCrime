from collections.abc import Generator
from pathlib import Path

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Connection, Engine

from backend.app.core.config import settings

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


def get_sqlite_url(raw_url: str) -> str:
    if raw_url.startswith("sqlite:///./"):
        rel_path = raw_url[len("sqlite:///./"):]
        abs_path = ROOT_DIR / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{abs_path}"
    return raw_url


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


_engine = None
metadata = MetaData()


def get_engine(db_url: str = None) -> Engine:
    global _engine
    if db_url is not None:
        return create_engine(get_sqlite_url(db_url), connect_args={"check_same_thread": False})
    if _engine is None:
        _engine = create_engine(get_sqlite_url(settings.DATABASE_URL), connect_args={"check_same_thread": False})
    return _engine


def get_connection() -> Generator[Connection, None, None]:
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


def reflect_metadata(engine: Engine = None) -> MetaData:
    eng = engine or get_engine()
    meta = MetaData()
    meta.reflect(bind=eng)
    return meta
