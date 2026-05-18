"""R2: 정규화 + cosine distance 단위 테스트.

목표:
1. 정규화 후 큰 스케일 feature 가 vector dominance 를 차지하지 않는다.
2. cosine distance 가 수동 계산값과 일치한다.
3. distance mode env 가 정상 동작한다.
"""
from __future__ import annotations
import math
import os
import importlib

from ml_server.retrieval.segment_builder import build_segment
from ml_server.retrieval import segment_embedding as SE
from ml_server.retrieval import retrieval_store as RS


def _snap(i, cpu=20.0, vram=0.0, pkt=0):
    return {
        "timestamp": f"2026-05-16T10:00:{i:02d}",
        "cpu_percent": cpu,
        "memory_percent": 50.0,
        "gpu_percent": 0.0,
        "gpu_vram_mb": vram,
        "gpu_power_w": 0.0,
        "disk_read_mb": 0.0,
        "disk_write_mb": 0.0,
        "inbound_mb": 0.0,
        "outbound_mb": 0.0,
        "external_packet_count": pkt,
    }


def _seg_meta(pc_id, slot, ts):
    return {
        "segment_id": f"{pc_id}:{slot}:{ts}",
        "pc_id": pc_id,
        "slot": slot,
        "start_ts": ts,
        "end_ts": ts,
        "window_size": 12,
        "snapshots": [],
    }


# ---------- 정규화 ----------

def test_normalize_removes_high_scale_dominance():
    """vram=10000, packet=5000 같은 큰 값이 cpu(20) 보다 dimension 을 압도하지 않아야 한다."""
    h = [_snap(i, cpu=20.0, vram=10000.0, pkt=5000) for i in range(12)]
    seg = build_segment("pc-1", "class", h)
    emb = SE.build_embedding(seg)

    # 모든 정규화 값은 [-2, 2] 범위 안 (실제로는 ~[0,1] 근처).
    for v in emb:
        assert -2.0 <= v <= 2.0, f"unnormalized value detected: {v}"

    # vram_mb 의 mean stat 과 cpu_percent 의 mean stat 차이가 10배 이하.
    # (raw 라면 500배 차이가 났을 것)
    cpu_mean = emb[0]               # cpu_percent stat[0]=mean
    vram_mean = emb[3 * 8 + 0]      # gpu_vram_mb mean stat
    assert vram_mean / max(cpu_mean, 1e-9) < 10.0, (
        f"vram still dominates: cpu_mean={cpu_mean} vram_mean={vram_mean}"
    )


def test_normalize_off_keeps_raw_scale():
    """RETRIEVAL_NORMALIZE=0 → raw 통계 그대로."""
    os.environ["RETRIEVAL_NORMALIZE"] = "0"
    try:
        importlib.reload(SE)
        h = [_snap(i, cpu=20.0, vram=10000.0) for i in range(12)]
        seg = build_segment("pc-1", "class", h)
        emb = SE.build_embedding(seg)
        vram_mean = emb[3 * 8 + 0]
        assert vram_mean > 1000.0, f"expected raw vram ~10000, got {vram_mean}"
    finally:
        os.environ["RETRIEVAL_NORMALIZE"] = "1"
        importlib.reload(SE)


# ---------- cosine distance ----------

def test_cosine_distance_manual():
    """수동 계산과 비교."""
    # a=[1,0,0], b=[0,1,0] → cos=0 → distance=1
    a = [1.0, 0.0, 0.0] + [0.0] * 77
    b = [0.0, 1.0, 0.0] + [0.0] * 77
    d = RS._cosine_distance(a, b)
    assert abs(d - 1.0) < 1e-6

    # a=[1,1,0] vs b=[1,1,0] → cos=1 → distance=0
    a2 = [1.0, 1.0, 0.0] + [0.0] * 77
    d2 = RS._cosine_distance(a2, a2)
    assert abs(d2 - 0.0) < 1e-6

    # opposite directions → cos=-1 → distance=2
    a3 = [1.0, 0.0] + [0.0] * 78
    b3 = [-1.0, 0.0] + [0.0] * 78
    d3 = RS._cosine_distance(a3, b3)
    assert abs(d3 - 2.0) < 1e-6


def test_cosine_distance_zero_vector_safe():
    a = [0.0] * 80
    b = [1.0] + [0.0] * 79
    d = RS._cosine_distance(a, b)
    assert d == 2.0


# ---------- mode env ----------

def test_distance_mode_env_switch():
    """RETRIEVAL_DISTANCE_MODE=euclidean → 기존 동작 (스케일 큰 게 더 멀다)."""
    RS.reset_store()
    a = [1.0] * 80
    b = [9.0] * 80
    c = [3.0] * 80
    RS.add_segment(_seg_meta("p-a", "class", "T1"), a, "NORMAL", 0.0)
    RS.add_segment(_seg_meta("p-b", "class", "T2"), b, "NORMAL", 0.0)
    RS.add_segment(_seg_meta("p-c", "class", "T3"), c, "NORMAL", 0.0)

    q = _seg_meta("pc-q", "class", "TQ")

    # cosine 모드: 모두 같은 방향 → distance 모두 0
    os.environ["RETRIEVAL_DISTANCE_MODE"] = "cosine"
    res_c = RS.search_similar(q, a, top_k=3)
    assert all(r["distance"] < 1e-3 for r in res_c)

    # euclidean 모드: 거리 정렬 가능
    os.environ["RETRIEVAL_DISTANCE_MODE"] = "euclidean"
    res_e = RS.search_similar(q, a, top_k=3)
    assert [r["pc_id"] for r in res_e] == ["p-a", "p-c", "p-b"]
    assert res_e[0]["distance"] < res_e[1]["distance"] < res_e[2]["distance"]

    # 정리
    os.environ["RETRIEVAL_DISTANCE_MODE"] = "cosine"
    RS.reset_store()


def test_topk_cosine_separates_pattern_not_magnitude():
    """패턴이 다른 벡터가 magnitude 가 비슷한 벡터보다 멀게 나와야 한다."""
    RS.reset_store()
    os.environ["RETRIEVAL_DISTANCE_MODE"] = "cosine"

    # query: cpu 축 강한 패턴
    query = [1.0, 0.0, 0.0, 0.0] + [0.0] * 76
    # 같은 패턴, magnitude 큼
    same_pattern_big = [50.0, 0.0, 0.0, 0.0] + [0.0] * 76
    # 다른 패턴, magnitude 비슷
    diff_pattern = [0.0, 1.0, 0.0, 0.0] + [0.0] * 76

    RS.add_segment(_seg_meta("same", "class", "T1"), same_pattern_big, "NORMAL", 0.0)
    RS.add_segment(_seg_meta("diff", "class", "T2"), diff_pattern, "NORMAL", 0.0)

    q = _seg_meta("pc-q", "class", "TQ")
    res = RS.search_similar(q, query, top_k=2)
    assert res[0]["pc_id"] == "same"
    assert res[1]["pc_id"] == "diff"
    # 첫 결과는 거리 0 근처, 두번째는 1.0 (orthogonal)
    assert res[0]["distance"] < 0.01
    assert abs(res[1]["distance"] - 1.0) < 0.01
