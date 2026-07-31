from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("CTRLV_DATA_DIR", ROOT / ".data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = ROOT / DATA_DIR

UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "ctrlv.sqlite"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
ALLOWED_ORIGINS = [
    value.strip()
    for value in os.getenv("CTRLV_ALLOWED_ORIGINS", "http://127.0.0.1:8765,http://localhost:8765").split(",")
    if value.strip()
]
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
