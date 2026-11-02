"""Database engine and session management."""

from collections.abc import Generator
import os
import re
import socket
import threading
from typing import Any
from urllib.parse import quote, unquote

from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import IS_SERVERLESS, WRITABLE_RUNTIME_DIR, get_settings

_DIRECT_SUPABASE_RE = re.compile(
    r"^postgresql\+psycopg://(?P<user>[^:@/]+):(?P<password>[^@/]+)@"
    r"db\.(?P<ref>[a-z0-9]+)\.supabase\.co(?::(?P<port>\d+))?/(?P<dbname>[^?]+)(?:\?(?P<query>.*))?$"
)


def _has_ipv4_record(hostname: str, port: int = 5432) -> bool:
    """Return True if hostname resolves to at least one IPv4 address."""
    try:
        infos = socket.getaddrinfo(hostname, port, socket.AF_INET)
        return len(infos) > 0
    except OSError:
        return False


def normalize_database_url(url: str) -> str:
    """Normalize Postgres connection strings to use the psycopg driver and IPv4 pooler when needed."""
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]

    match = _DIRECT_SUPABASE_RE.match(url)
    if match:
        ref = match.group("ref")
        direct_host = f"db.{ref}.supabase.co"
        port = int(match.group("port") or "5432")
        if IS_SERVERLESS or not _has_ipv4_record(direct_host, port):
            user = unquote(match.group("user"))
            password = quote(unquote(match.group("password")), safe="")
            dbname = match.group("dbname")
            pooler_host = os.environ.get(
                "SUPABASE_POOLER_HOST", "aws-0-eu-west-1.pooler.supabase.com"
            )
            pooler_user = user if "." in user else f"{user}.{ref}"
            url = (
                f"postgresql+psycopg://{pooler_user}:{password}"
                f"@{pooler_host}:6543/{dbname}?sslmode=require"
            )

    return url


def build_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured DATABASE_URL."""
    raw_url = database_url or get_settings().DATABASE_URL
    url = normalize_database_url(raw_url)

    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if url.startswith("sqlite:///") and ":memory:" not in url:
            sqlite_file_str = url[len("sqlite:///") :].split("?", 1)[0]
            if sqlite_file_str:
                try:
                    from pathlib import Path

                    Path(sqlite_file_str).parent.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
    elif url.startswith("postgresql"):
        connect_args["prepare_threshold"] = None
        connect_args["connect_timeout"] = 10

    if url.startswith("postgresql"):
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=15,
            max_overflow=20,
            pool_recycle=300,
            connect_args=connect_args,
        )
    else:
        engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_runtime_db_initialized = False
_runtime_db_lock = threading.Lock()


def _ensure_runtime_database_ready() -> None:
    """Ensure the runtime database is reachable, migrated, and seeded with baseline demo data."""
    global engine, SessionLocal, _runtime_db_initialized
    if _runtime_db_initialized:
        return

    with _runtime_db_lock:
        if _runtime_db_initialized:
            return

        from app.db.base import Base
        from app.db.models import Clinician
        from app.scripts.seed import seed_demo_longitudinal

        try:
            with SessionLocal() as check_db:
                clinician_count = check_db.scalar(
                    select(func.count()).select_from(Clinician)
                )
                if clinician_count and clinician_count > 0:
                    _runtime_db_initialized = True
                    return
        except SQLAlchemyError:
            if IS_SERVERLESS:
                fallback_dir = WRITABLE_RUNTIME_DIR
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fallback_url = f"sqlite:///{(fallback_dir / 'dermobridge.db').as_posix()}"
                engine = build_engine(fallback_url)
                SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        try:
            Base.metadata.create_all(bind=engine)
            with SessionLocal() as seed_db:
                clinician_count = seed_db.scalar(
                    select(func.count()).select_from(Clinician)
                )
                if not clinician_count:
                    seed_demo_longitudinal(seed_db)
            _runtime_db_initialized = True
        except SQLAlchemyError:
            # Leave uninitialized so explicit health checks can surface DB errors if non-serverless
            pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    _ensure_runtime_database_ready()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
