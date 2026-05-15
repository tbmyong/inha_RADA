"""Retrieval-Augmented Time-Series Evidence Layer.

논문 적용 매뉴얼 7단계 구현. statistical embedding 기반 segment 검색.
"""
from .segment_builder import build_segment
from .segment_embedding import build_embedding
from .retrieval_store import (
    add_segment,
    search_similar,
    clear_pc,
    reset_store,
    segment_history_by_slot,
)
from .retrieval_evidence import build_retrieval_evidence

__all__ = [
    "build_segment",
    "build_embedding",
    "add_segment",
    "search_similar",
    "clear_pc",
    "reset_store",
    "segment_history_by_slot",
    "build_retrieval_evidence",
]
