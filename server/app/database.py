from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .database_tuning import configure_sqlite_engine
from .indexing.sqlite_fts import init_knowledge_search_index
from .migrations import run_migrations
from .settings import settings


def ensure_data_dirs() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
configure_sqlite_engine(engine)


def init_search_index() -> None:
    init_knowledge_search_index(engine)


def init_db() -> None:
    ensure_data_dirs()
    run_migrations(engine)
    SQLModel.metadata.create_all(engine)
    init_search_index()


def get_session():
    with Session(engine) as session:
        yield session
