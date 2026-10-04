"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Configure test env before importing the app
os.environ["VIDKIT_DISABLE_SCHEDULER"] = "1"
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("STORAGE_DIR", str(Path(__file__).parent / "_test_storage"))
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.services.storage import ensure_storage_dirs

get_settings.cache_clear()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import models so metadata is populated
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session, tmp_path: Path) -> Generator[TestClient, None, None]:
    os.environ["STORAGE_DIR"] = str(tmp_path / "storage")
    get_settings.cache_clear()
    ensure_storage_dirs()

    def _override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()
