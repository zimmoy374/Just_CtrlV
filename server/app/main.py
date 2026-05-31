from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .analysis.jobs import run_recoverable_analysis_jobs
from .database import init_db
from .routes import agent, cards, knowledge, memory, review, system, tasks
from .settings import settings


init_db()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    Thread(target=run_recoverable_analysis_jobs, daemon=True).start()
    yield


app = FastAPI(title="second brain", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8765", "http://localhost:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"ok": "true"}


app.include_router(cards.router)
app.include_router(knowledge.router)
app.include_router(memory.router)
app.include_router(tasks.router)
app.include_router(agent.router)
app.include_router(review.router)
app.include_router(system.router)
