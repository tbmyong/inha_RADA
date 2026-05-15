"""Retrieval segment builder + embedding 단위 테스트."""
from collections import deque

from ml_server.retrieval.segment_builder import build_segment
from ml_server.retrieval.segment_embedding import build_embedding, EMBED_DIM


def _snap(i: int, **over):
    base = {
        "timestamp": f"2026-05-16T10:00:{i:02d}",
        "cpu_percent": 10.0 + i,
        "memory_percent": 20.0,
        "gpu_percent": 0.0,
        "gpu_vram_mb": 0.0,
        "gpu_power_w": 0.0,
        "disk_read_mb": 0.1,
        "disk_write_mb": 0.1,
        "inbound_mb": 0.0,
        "outbound_mb": 0.0,
        "external_packet_count": 0,
    }
    base.update(over)
    return base


def test_segment_none_when_insufficient():
    h = deque([_snap(i) for i in range(5)])
    assert build_segment("pc-1", "class", h, window_size=12) is None


def test_segment_built_when_sufficient():
    h = deque([_snap(i) for i in range(12)])
    seg = build_segment("pc-1", "class", h, window_size=12)
    assert seg is not None
    assert seg["pc_id"] == "pc-1"
    assert seg["slot"] == "class"
    assert seg["window_size"] == 12
    assert len(seg["snapshots"]) == 12
    assert seg["start_ts"] and seg["end_ts"]


def test_embedding_fixed_length_and_finite():
    h = [_snap(i) for i in range(12)]
    seg = build_segment("pc-1", "class", h)
    emb = build_embedding(seg)
    assert len(emb) == EMBED_DIM
    import math
    for v in emb:
        assert isinstance(v, float)
        assert not math.isnan(v) and not math.isinf(v)


def test_embedding_handles_missing_gpu():
    h = [_snap(i, gpu_percent=None, gpu_vram_mb=None) for i in range(12)]
    seg = build_segment("pc-1", "class", h)
    emb = build_embedding(seg)
    assert len(emb) == EMBED_DIM
