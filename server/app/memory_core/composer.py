from __future__ import annotations

from typing import Any

from sqlmodel import Session

from ..context.packs import build_context_pack
from .protocol import MemoryQuery, MemorySlice
from .router import MemoryRouter, create_default_memory_router


class MemoryContextComposer:
    def __init__(self, router: MemoryRouter | None = None) -> None:
        self.router = router or create_default_memory_router()

    def retrieve_slices(self, session: Session, query: MemoryQuery) -> list[MemorySlice]:
        return self.router.retrieve(session, query)

    def build_context_pack(
        self,
        session: Session,
        *,
        query: str,
        max_pages: int = 3,
        max_items: int = 6,
        max_source_excerpts: int = 3,
        max_chars: int = 4000,
    ) -> dict[str, Any]:
        return build_context_pack(
            session,
            query=query,
            max_pages=max_pages,
            max_items=max_items,
            max_source_excerpts=max_source_excerpts,
            max_chars=max_chars,
        )
