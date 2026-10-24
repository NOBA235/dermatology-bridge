"""Pytest fixtures for Dermatology Bridge backend tests."""

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config import API_ROOT
from app.db.session import build_engine, get_db
from app.main import create_app


@pytest.fixture()
def migrated_db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Create a clean temporary database, apply Alembic migration in one command, and yield Session."""
    db_file = tmp_path / "test_phase0.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    alembic_cfg = Config(str(API_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Apply migration to clean DB in one command
    command.upgrade(alembic_cfg, "head")

    engine = build_engine(db_url)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(migrated_db_session: Session) -> Generator[TestClient, None, None]:
    """Return a FastAPI TestClient wired to the migrated temporary database."""
    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        yield migrated_db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client

