from __future__ import annotations

from collections.abc import Iterable


def reciprocal_rank_fusion(rankings: Iterable[list[str]], *, k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            if not item_id:
                continue
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores
