from __future__ import annotations

import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import blake2b
from threading import RLock
from typing import ClassVar

from ..core.text import normalize_keyword
from ..models import KnowledgeItem


DEFAULT_VECTOR_DIMENSIONS = 512


@dataclass(frozen=True)
class VectorCandidate:
    knowledge_item_id: str
    score: float
    matched_features: list[str]


@dataclass(frozen=True)
class _CollectionIndex:
    item_vectors: dict[str, tuple[dict[int, float], set[str]]]
    feature_to_item_ids: dict[str, set[str]]


class LocalVectorSearch:
    """Small local vector recall layer.

    This is intentionally deterministic and dependency-free. It gives the
    retrieval pipeline a replaceable vector-recall interface without requiring
    a cloud embedding API or external vector database.
    """

    _item_vector_cache: ClassVar[OrderedDict[str, tuple[dict[int, float], set[str]]]] = OrderedDict()
    _collection_cache: ClassVar[OrderedDict[str, _CollectionIndex]] = OrderedDict()
    _max_cache_entries: ClassVar[int] = 2048
    _max_collection_cache_entries: ClassVar[int] = 4
    _cache_lock: ClassVar[RLock] = RLock()

    def __init__(self, dimensions: int = DEFAULT_VECTOR_DIMENSIONS, min_score: float = 0.10) -> None:
        self.dimensions = dimensions
        self.min_score = min_score

    @classmethod
    def clear_cache(cls) -> None:
        with cls._cache_lock:
            cls._item_vector_cache.clear()
            cls._collection_cache.clear()

    def search(
        self,
        knowledge_items: list[KnowledgeItem],
        query: str,
        *,
        limit: int,
        collection_cache_key: str | None = None,
    ) -> list[VectorCandidate]:
        query_vector, query_features = self._text_vector(query)
        if not query_vector:
            return []
        min_score = 0.82 if _has_cjk(query) else self.min_score
        collection = self._collection_index(knowledge_items, collection_cache_key=collection_cache_key)
        candidate_ids: set[str] = set()
        for feature in query_features:
            candidate_ids.update(collection.feature_to_item_ids.get(feature, set()))
        if not candidate_ids:
            return []

        candidates: list[VectorCandidate] = []
        for item_id in candidate_ids:
            item_vector, item_features = collection.item_vectors[item_id]
            if not item_vector:
                continue
            score = _cosine_similarity(query_vector, item_vector)
            if score < min_score:
                continue
            matched_features = sorted((query_features & item_features), key=lambda value: (-len(value), value))[:6]
            candidates.append(VectorCandidate(item_id, score, matched_features))

        candidates.sort(key=lambda item: (-item.score, item.knowledge_item_id))
        return candidates[:limit]

    def _collection_index(self, knowledge_items: list[KnowledgeItem], *, collection_cache_key: str | None) -> _CollectionIndex:
        cache_key = collection_cache_key
        if cache_key is None:
            item_cache_keys = [self._item_cache_key(item) for item in knowledge_items]
            cache_key = self._collection_cache_key(item_cache_keys)
        with self._cache_lock:
            cached = self._collection_cache.get(cache_key)
            if cached is not None:
                self._collection_cache.move_to_end(cache_key)
                return cached

        item_vectors: dict[str, tuple[dict[int, float], set[str]]] = {}
        feature_to_item_ids: dict[str, set[str]] = {}
        for item in knowledge_items:
            vector, features = self._item_vector(item)
            if not vector:
                continue
            item_vectors[item.id] = (vector, features)
            for feature in features:
                feature_to_item_ids.setdefault(feature, set()).add(item.id)

        collection = _CollectionIndex(item_vectors=item_vectors, feature_to_item_ids=feature_to_item_ids)
        with self._cache_lock:
            self._collection_cache[cache_key] = collection
            if len(self._collection_cache) > self._max_collection_cache_entries:
                self._collection_cache.popitem(last=False)
        return collection

    def _item_vector(self, item: KnowledgeItem) -> tuple[dict[int, float], set[str]]:
        cache_key = self._item_cache_key(item)
        with self._cache_lock:
            cached = self._item_vector_cache.get(cache_key)
            if cached is not None:
                self._item_vector_cache.move_to_end(cache_key)
                return cached

        weighted_parts = [
            (item.title or "", 3.0),
            (item.summary or "", 2.0),
            (" ".join(item.keywords or []), 3.0),
            (item.content or "", 1.0),
        ]
        vector: dict[int, float] = {}
        features: set[str] = set()
        for text, weight in weighted_parts:
            part_vector, part_features = self._text_vector(text, weight=weight)
            features.update(part_features)
            for index, value in part_vector.items():
                vector[index] = vector.get(index, 0.0) + value
        result = (vector, features)
        with self._cache_lock:
            self._item_vector_cache[cache_key] = result
            if len(self._item_vector_cache) > self._max_cache_entries:
                self._item_vector_cache.popitem(last=False)
        return result

    def _text_vector(self, text: str, *, weight: float = 1.0) -> tuple[dict[int, float], set[str]]:
        features = _features(text)
        vector: dict[int, float] = {}
        for feature in features:
            index = _stable_hash(feature) % self.dimensions
            vector[index] = vector.get(index, 0.0) + weight
        return vector, set(features)

    def _item_cache_key(self, item: KnowledgeItem) -> str:
        digest = blake2b(digest_size=16)
        for value in [item.title, item.summary, item.content, " ".join(item.keywords or [])]:
            digest.update((value or "").encode("utf-8"))
            digest.update(b"\0")
        updated_at = item.updated_at.isoformat() if item.updated_at else ""
        return f"{self.dimensions}:{item.id}:{updated_at}:{digest.hexdigest()}"

    def _collection_cache_key(self, item_cache_keys: list[str]) -> str:
        digest = blake2b(digest_size=16)
        for key in item_cache_keys:
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
        return f"{self.dimensions}:{len(item_cache_keys)}:{digest.hexdigest()}"


def _features(text: str) -> list[str]:
    raw_text = text or ""
    normalized = normalize_keyword(raw_text)
    words = [
        word.casefold()
        for word in re.findall(r"[A-Za-z0-9]+", raw_text)
        if len(word) > 1 and not word.isdigit() and word.casefold() not in _GENERIC_WORDS
    ]
    features: list[str] = []
    features.extend(f"w:{word}" for word in words)
    features.extend(f"b:{words[index]}_{words[index + 1]}" for index in range(0, max(0, len(words) - 1)))
    if normalized and (_has_cjk(raw_text) or not words):
        for size in (2, 3, 4):
            if len(normalized) <= size:
                features.append(f"c:{normalized}")
                continue
            features.extend(f"c:{normalized[index:index + size]}" for index in range(0, len(normalized) - size + 1))
    return list(dict.fromkeys(features))


_GENERIC_WORDS = {
    "challenge",
    "eval",
    "evaluation",
    "note",
    "retrieval",
    "target",
    "topic",
}


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _stable_hash(value: str) -> int:
    result = 2166136261
    for byte in value.encode("utf-8"):
        result ^= byte
        result = (result * 16777619) & 0xFFFFFFFF
    return result


def _cosine_similarity(left: dict[int, float], right: dict[int, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(index, 0.0) for index, value in left.items())
    if dot <= 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)
