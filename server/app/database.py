from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .settings import settings


def ensure_data_dirs() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    ensure_data_dirs()
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
