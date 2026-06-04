from __future__ import annotations

from dataclasses import dataclass, field

from ..models import KnowledgeItem


@dataclass
class RetrievalCandidate:
    knowledge_item: KnowledgeItem
    lexical_score: float = 0.0
    vector_score: float = 0.0
    fusion_score: float = 0.0
    matched_fields: list[str] = field(default_factory=list)
    vector_features: list[str] = field(default_factory=list)
    used_lexical: bool = False
    used_vector: bool = False


def rerank_candidate(candidate: RetrievalCandidate) -> float:
    lexical_component = _lexical_component(candidate)
    vector_component = min(95.0, candidate.vector_score * 110.0)
    base_component = max(lexical_component, vector_component)
    fusion_component = candidate.fusion_score * 900.0
    type_bonus = _knowledge_type_bonus(candidate.knowledge_item.knowledge_type)
    evidence_bonus = 3.0 if candidate.knowledge_item.source_item_id else 0.0
    keyword_bonus = 3.0 if any(field.startswith("关键词：") for field in candidate.matched_fields) else 0.0
    hybrid_bonus = 2.0 if candidate.used_lexical and candidate.used_vector else 0.0
    return base_component + fusion_component + type_bonus + evidence_bonus + keyword_bonus + hybrid_bonus


def _knowledge_type_bonus(knowledge_type: str) -> float:
    if knowledge_type in {"rule_preference", "procedure_lesson"}:
        return 2.0
    return 0.0


def _lexical_component(candidate: RetrievalCandidate) -> float:
    strong_fields = {field for field in candidate.matched_fields if field not in {"全文索引", "向量召回", "RRF融合"}}
    if strong_fields:
        return candidate.lexical_score
    if "全文索引" in candidate.matched_fields:
        return min(candidate.lexical_score, 35.0)
    return 0.0
