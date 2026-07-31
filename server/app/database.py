from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .database_tuning import configure_sqlite_engine
from .settings import settings


def ensure_data_dirs() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
configure_sqlite_engine(engine)


def init_db() -> None:
    ensure_data_dirs()
    SQLModel.metadata.create_all(engine)
    _ensure_daily_card_fields()


def _ensure_daily_card_fields() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("cards")}
    with engine.begin() as connection:
        if "day_key" not in columns:
            connection.execute(text("ALTER TABLE cards ADD COLUMN day_key VARCHAR NOT NULL DEFAULT ''"))
            connection.execute(
                text(
                    "UPDATE cards SET day_key = CASE "
                    "WHEN created_at IS NOT NULL THEN substr(created_at, 1, 10) "
                    "ELSE date('now', 'localtime') END WHERE day_key = ''",
                ),
            )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_cards_day_key ON cards(day_key)"))
        connection.execute(
            text(
                "UPDATE cards SET "
                "x = CASE WHEN x > 1 THEN min(0.78, max(0.03, x / 1280.0)) ELSE x END, "
                "y = CASE WHEN y > 1 THEN min(0.72, max(0.04, y / 720.0)) ELSE y END",
            ),
        )


def get_session():
    with Session(engine) as session:
        yield session
