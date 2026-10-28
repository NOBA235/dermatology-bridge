"""Alembic migration environment configured against app.db.models."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.config import get_settings
from app.db.base import Base
import app.db.models  # noqa: F401 — ensure all models are registered on Base.metadata
from app.db.session import build_engine, normalize_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    """Resolve database URL from alembic config override or pydantic-settings."""
    configured = config.get_main_option("sqlalchemy.url")
    raw_url = configured if configured else get_settings().DATABASE_URL
    return normalize_database_url(raw_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        engine = build_engine(get_database_url())
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
