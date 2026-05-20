"""R4 — Retrieval quality validation on real local traffic.

목적
-----
합성 90-segment 시뮬레이션이 아니라, 실제 백그라운드 client.py 가 ~1h 쌓은
metrics_history (pc_id=0c7a15737f66, ~746 row) + tools/anomaly_trigger.py 의
mining payload 를 같이 retrieval_store 에 통과시켜 3 모드 (A/B/C) 간 분리도와
FP 비율을 정량 비교한다.

3 모드:
  - A : retrieval OFF (단순 baseline; mining payload 만 평가)
  - B : retrieval ON  + RETRIEVAL_DISTANCE_MODE=euclidean + RETRIEVAL_NORMALIZE=0
  - C : retrieval ON  + RETRIEVAL_DISTANCE_MODE=cosine    + RETRIEVAL_NORMALIZE=1  (default)

회귀 안전성: ml_server 모듈은 직접 import 만 한다 (docker 컨테이너 영향 0).
DB 는 read-only.
"""
from __future__ import annotations
import json
import os
import sys
import math
import random
import statistics
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

# 프로젝트 루트를 sys.path 에 추가
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import subprocess  # noqa: E402

TARGET_PC = "0c7a15737f66"
WINDOW = 12   # 12 snapshot = 1 segment (1 분)
TOP_K = 3
RNG_SEED = 42

PG_CONTAINER = os.environ.get("RADA_PG_CONTAINER", "rada-postgres")
PG_USER = os.environ.get("RADA_PG_USER", "rada")
PG_DB   = os.environ.get("RADA_PG_DB", "pc_monitor")


# ----------------------------------------------------------------------
# 1. DB 로드 (docker exec psql 경유, 외부 dependency 불필요)
# ----------------------------------------------------------------------
def load_metric_rows(pc_id: str) -> List[dict]:
    # gpu_power_w / external_packet_count 는 extra(jsonb) 안에 있으므로 추출.
    sql = (
        "SELECT collected_at, COALESCE(cpu_percent,0), COALESCE(mem_percent,0), "
        "COALESCE(gpu_percent,0), COALESCE(vram_mb,0), "
        "COALESCE((extra->>'gpu_power_w')::float, 0), "
        "COALESCE(disk_read_mb,0), COALESCE(disk_write_mb,0), "
        "COALESCE(inbound_mb,0), COALESCE(outbound_mb,0), "
        "COALESCE((extra->>'external_packet_count')::float, 0) "
        f"FROM pc_monitor.metrics_history WHERE pc_id='{pc_id}' "
        "ORDER BY collected_at ASC"
    )
    proc = subprocess.run(
        ["docker", "exec", "-i", PG_CONTAINER,
         "psql", "-U", PG_USER, "-d", PG_DB, "-At", "-F", ",", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"psql failed: {proc.stderr[:500]}")
    rows: List[dict] = []
    for line in proc.stdout.splitlines():
        parts = line.split(",")
        if len(parts) < 11:
            continue
        rows.append({
            "timestamp":             parts[0],
            "cpu_percent":           float(parts[1] or 0.0),
            "memory_percent":        float(parts[2] or 0.0),
            "gpu_percent":           float(parts[3] or 0.0),
            "gpu_vram_mb":           float(parts[4] or 0.0),
            "gpu_power_w":           float(parts[5] or 0.0),
            "disk_read_mb":          float(parts[6] or 0.0),
            "disk_write_mb":         float(parts[7] or 0.0),
            "inbound_mb":            float(parts[8] or 0.0),
            "outbound_mb":           float(parts[9] or 0.0),
            "external_packet_count": float(parts[10] or 0.0),
        })
    return rows


def baseline_stats(rows: List[dict]) -> dict:
    def stat(key: str) -> dict:
        vals = [r[key] for r in rows]
        if not vals:
            return {"mean": 0, "p50": 0, "p95": 0, "max": 0}
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        p50 = vals_sorted[n // 2]
        p95 = vals_sorted[min(n - 1, int(0.95 * n))]
        return {
            "mean": round(statistics.fmean(vals), 3),
            "p50":  round(p50, 3),
            "p95":  round(p95, 3),
            "max":  round(max(vals), 3),
        }
    return {k: stat(k) for k in (
        "cpu_percent", "memory_percent",
        "disk_read_mb", "disk_write_mb",
        "inbound_mb", "outbound_mb",
        "external_packet_count",
    )}


# ----------------------------------------------------------------------
# 2. segment 생성 (sliding window)
# ----------------------------------------------------------------------
def rows_to_segments(rows: List[dict], pc_id: str, slot: str = "free",
                     stride: int = 6) -> List[dict]:
    """rows 를 WINDOW 크기 sliding window 로 잘라 segment 리스트로 변환.
    stride=6 → 30 초 겹치는 segment.
    """
    segs: List[dict] = []
    for i in range(0, len(rows) - WINDOW + 1, stride):
        window = rows[i:i + WINDOW]
        start_ts = window[0]["timestamp"]
        end_ts = window[-1]["timestamp"]
        segs.append({
            "segment_id": f"{pc_id}:{slot}:{start_ts}",
            "pc_id": pc_id,
            "slot": slot,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "window_size": WINDOW,
            "snapshots": window,
        })
    return segs


def mining_segment(pc_id: str = "pc-smoke", slot: str = "free") -> dict:
    """anomaly_trigger.py 의 mining payload 와 동일한 분포의 snapshot 12 개.
    실제 컨테이너로 보내는 대신 in-process segment 로 만든다.
    """
    snaps = []
    for i in range(WINDOW):
        snaps.append({
            "timestamp":             f"2026-05-20T17:35:{i:02d}+09:00",
            "cpu_percent":           96.0 + (i % 3),
            "memory_percent":        82.0,
            "gpu_percent":           95.0 + (i % 5),
            "gpu_vram_mb":           7800.0,
            "gpu_power_w":           165.0,
            "disk_read_mb":          8.0,
            "disk_write_mb":         5.0,
            "inbound_mb":            0.5,
            "outbound_mb":           12.0,
            "external_packet_count": 1200 + i * 50,
        })
    return {
        "segment_id": f"{pc_id}:{slot}:mining-{random.random():.6f}",
        "pc_id": pc_id,
        "slot": slot,
        "start_ts": snaps[0]["timestamp"],
        "end_ts":   snaps[-1]["timestamp"],
        "window_size": WINDOW,
        "snapshots": snaps,
    }


# ----------------------------------------------------------------------
# 3. mode-aware retrieval 평가
# ----------------------------------------------------------------------
def set_mode_env(mode: str) -> None:
    """mode= 'A' (off) | 'B' (euclid raw) | 'C' (cosine norm)."""
    # A 는 실제론 retrieval 호출을 안함. B/C 만 env 영향.
    if mode == "B":
        os.environ["RETRIEVAL_DISTANCE_MODE"] = "euclidean"
        os.environ["RETRIEVAL_NORMALIZE"] = "0"
    elif mode == "C":
        os.environ["RETRIEVAL_DISTANCE_MODE"] = "cosine"
        os.environ["RETRIEVAL_NORMALIZE"] = "1"
    # store 의 _NORMALIZE 는 모듈 import 시점에 결정되므로 reload 필요
    import importlib
    from ml_server.retrieval import segment_embedding as se
    importlib.reload(se)
    # store / evidence 도 다시 import (distance mode 는 매 호출에서 env 읽으므로 reload 불필요)


def run_mode(mode: str, normal_segments: List[dict],
             mining_segments: List[dict]) -> dict:
    """단일 모드 평가.

    절차:
      1. store reset
      2. normal_segments (NORMAL verdict, score 0) 누적
      3. mining_segments 각각에 대해 search_similar 호출 → distance, verdict 분포
      4. FP: normal_segments 중 50 개 sampling → search 호출 → top-1 verdict 가
         HIGH_RISK 면 FP. 그러나 mode A 는 retrieval 자체를 안 함.
    """
    set_mode_env(mode)
    # 함수는 import 시점에 env 를 읽지 않고 호출시 읽으므로 한 번만 import 해도 됨
    from ml_server.retrieval.retrieval_store import (
        reset_store, add_segment, search_similar,
    )
    from ml_server.retrieval.segment_embedding import build_embedding
    from ml_server.retrieval.retrieval_evidence import build_retrieval_evidence

    reset_store()

    # store 초기 채움 — 절반은 NORMAL, 일부 HIGH_RISK 로 라벨 (정상 traffic 자체는
    # 다 정상이지만 retrieval 의 verdict 라벨 다양성 확보 위해 mining 도 일부 미리 넣음).
    PREPOP_MINING = 5
    seeded_mining = mining_segments[:PREPOP_MINING]
    held_mining = mining_segments[PREPOP_MINING:]

    for seg in normal_segments:
        emb = build_embedding(seg)
        add_segment(seg, emb, verdict="NORMAL", score=0.0)
    for seg in seeded_mining:
        emb = build_embedding(seg)
        add_segment(seg, emb, verdict="HIGH_RISK", score=14.0)

    # mining query → distance / verdict 분포
    mining_results = []
    for seg in held_mining:
        emb = build_embedding(seg)
        if mode == "A":
            # off → retrieval 호출 안 함
            mining_results.append({
                "top1_distance": None,
                "top1_verdict": None,
                "retrieval_score": 0,
                "high_risk_in_topk": 0,
            })
            continue
        hits = search_similar(seg, emb, top_k=TOP_K)
        ev = build_retrieval_evidence(seg, hits)
        top1 = hits[0] if hits else None
        mining_results.append({
            "top1_distance": top1["distance"] if top1 else None,
            "top1_verdict": top1["verdict"] if top1 else None,
            "retrieval_score": ev["retrieval_score"],
            "high_risk_in_topk": ev["similar_high_risk_count"],
        })

    # FP 측정: 정상 segment N개 무작위 → 자기 자신은 store 에 들어있지만 search 가
    # self skip 하므로 다른 정상/주입된 mining 과 비교됨.
    rng = random.Random(RNG_SEED)
    sample_n = min(50, len(normal_segments))
    samples = rng.sample(normal_segments, sample_n)
    fp_results = []
    fp_count = 0
    for seg in samples:
        if mode == "A":
            fp_results.append({"top1_distance": None, "top1_verdict": None})
            continue
        emb = build_embedding(seg)
        hits = search_similar(seg, emb, top_k=TOP_K)
        top1 = hits[0] if hits else None
        verdict = top1["verdict"] if top1 else None
        fp_results.append({
            "top1_distance": top1["distance"] if top1 else None,
            "top1_verdict": verdict,
        })
        if verdict == "HIGH_RISK":
            fp_count += 1

    # 집계
    def _agg(xs: List[float]) -> dict:
        xs = [x for x in xs if x is not None]
        if not xs:
            return {"n": 0}
        return {
            "n": len(xs),
            "mean": round(statistics.fmean(xs), 4),
            "std":  round(statistics.pstdev(xs), 4) if len(xs) > 1 else 0.0,
            "min":  round(min(xs), 4),
            "max":  round(max(xs), 4),
        }

    # 추가 측정: mining query vs normal-only store (분리도) ----------
    reset_store()
    for seg in normal_segments:
        emb = build_embedding(seg)
        add_segment(seg, emb, verdict="NORMAL", score=0.0)
    sep_distances = []
    if mode != "A":
        for seg in mining_segments:
            emb = build_embedding(seg)
            hits = search_similar(seg, emb, top_k=1)
            if hits:
                sep_distances.append(hits[0]["distance"])
    # 정상 segment 들끼리의 평균 거리 (참고용 within-class)
    within_normal_distances = []
    if mode != "A":
        rng2 = random.Random(RNG_SEED + 1)
        sample_for_within = rng2.sample(normal_segments,
                                        min(30, len(normal_segments)))
        for seg in sample_for_within:
            emb = build_embedding(seg)
            hits = search_similar(seg, emb, top_k=1)
            if hits:
                within_normal_distances.append(hits[0]["distance"])

    def _agg2(xs):
        xs = [x for x in xs if x is not None]
        if not xs:
            return {"n": 0}
        return {
            "n": len(xs),
            "mean": round(statistics.fmean(xs), 4),
            "std":  round(statistics.pstdev(xs), 4) if len(xs) > 1 else 0.0,
            "min":  round(min(xs), 4),
            "max":  round(max(xs), 4),
        }

    separation = {
        "mining_to_normal_topk":  _agg2(sep_distances),
        "normal_to_normal_topk":  _agg2(within_normal_distances),
    }
    if separation["normal_to_normal_topk"].get("n") and separation["mining_to_normal_topk"].get("n"):
        nm = separation["normal_to_normal_topk"]["mean"] or 1e-9
        mm = separation["mining_to_normal_topk"]["mean"]
        separation["separability_ratio"] = round(mm / nm, 3) if nm else None

    return {
        "mode": mode,
        "separation": separation,
        "mining": {
            "n": len(mining_results),
            "top1_distance":    _agg([r["top1_distance"] for r in mining_results]),
            "retrieval_score":  _agg([r["retrieval_score"] for r in mining_results]),
            "top1_verdict_high_risk_rate": (
                round(sum(1 for r in mining_results
                          if r["top1_verdict"] == "HIGH_RISK") / max(1, len(mining_results)), 3)
            ),
        },
        "fp": {
            "n": sample_n,
            "fp_count": fp_count,
            "fp_rate":  round(fp_count / max(1, sample_n), 3),
            "top1_distance": _agg([r["top1_distance"] for r in fp_results]),
        },
    }


# ----------------------------------------------------------------------
# 4. main
# ----------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pc", default=TARGET_PC)
    parser.add_argument("--out", default=None,
                        help="JSON 결과 저장 경로 (옵션)")
    args = parser.parse_args(argv)

    rows = load_metric_rows(args.pc)
    if len(rows) < WINDOW * 2:
        print(f"[ERR] not enough rows for {args.pc}: {len(rows)}", file=sys.stderr)
        return 2
    base_stats = baseline_stats(rows)
    print(f"[load] pc={args.pc} rows={len(rows)}")
    print(f"[baseline] {json.dumps(base_stats, ensure_ascii=False)}")

    normal_segs = rows_to_segments(rows, args.pc, slot="free", stride=6)
    print(f"[segments] normal={len(normal_segs)}")

    random.seed(RNG_SEED)
    mining_segs = [mining_segment() for _ in range(15)]
    print(f"[segments] mining={len(mining_segs)}")

    out = {
        "pc_id": args.pc,
        "rows":  len(rows),
        "normal_segments": len(normal_segs),
        "mining_segments": len(mining_segs),
        "baseline": base_stats,
        "modes": {},
    }
    for mode in ("A", "B", "C"):
        print(f"[mode {mode}] running…")
        out["modes"][mode] = run_mode(mode, normal_segs, mining_segs)
        print(f"[mode {mode}] result: "
              f"mining_top1_dist={out['modes'][mode]['mining']['top1_distance']} "
              f"fp_rate={out['modes'][mode]['fp']['fp_rate']}")

    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[write] {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
