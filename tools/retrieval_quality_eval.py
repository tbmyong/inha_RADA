"""R2: Retrieval quality evaluation.

합성 데이터로 정상 / mining / training 시나리오 각 30개를 만들고,
Euclidean(raw) 모드와 Cosine(normalized) 모드 의 Recall@5 / Precision@5 /
Separability 를 비교한 뒤 docs/retrieval_quality_report.md 에 저장한다.

deterministic: seed=42.
"""
from __future__ import annotations
import os
import sys
import random
import importlib
import math
from pathlib import Path
from typing import List, Tuple, Dict

# repo root sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


SCENARIOS = ("normal", "mining", "training")
PER_SCENARIO = 30
SEED = 42
WINDOW = 12


def _gen_snapshot(scn: str, rng: random.Random, i: int) -> dict:
    """scn 별 한 snapshot. 시간 i 의 jitter 가 들어간다."""
    if scn == "normal":
        return {
            "timestamp": f"2026-05-18T10:00:{i:02d}",
            "cpu_percent":           rng.uniform(10.0, 30.0),
            "memory_percent":        rng.uniform(60.0, 80.0),
            "gpu_percent":           rng.uniform(0.0, 5.0),
            "gpu_vram_mb":           rng.uniform(200.0, 800.0),
            "gpu_power_w":           rng.uniform(10.0, 30.0),
            "disk_read_mb":          rng.uniform(0.0, 2.0),
            "disk_write_mb":         rng.uniform(0.0, 2.0),
            "inbound_mb":            rng.uniform(0.0, 1.0),
            "outbound_mb":           rng.uniform(0.0, 0.5),
            "external_packet_count": rng.randint(0, 20),
        }
    if scn == "mining":
        return {
            "timestamp": f"2026-05-18T10:00:{i:02d}",
            "cpu_percent":           rng.uniform(90.0, 99.0),
            "memory_percent":        rng.uniform(50.0, 70.0),
            "gpu_percent":           rng.uniform(90.0, 99.0),
            "gpu_vram_mb":           rng.uniform(6000.0, 12000.0),
            "gpu_power_w":           rng.uniform(180.0, 320.0),
            "disk_read_mb":          rng.uniform(0.0, 0.5),
            "disk_write_mb":         rng.uniform(0.0, 0.5),
            "inbound_mb":            rng.uniform(0.5, 3.0),
            "outbound_mb":           rng.uniform(0.5, 4.0),
            "external_packet_count": rng.randint(800, 3000),
        }
    # training
    return {
        "timestamp": f"2026-05-18T10:00:{i:02d}",
        "cpu_percent":           rng.uniform(70.0, 85.0),
        "memory_percent":        rng.uniform(50.0, 70.0),
        "gpu_percent":           rng.uniform(60.0, 85.0),
        "gpu_vram_mb":           rng.uniform(4000.0, 9000.0),
        "gpu_power_w":           rng.uniform(120.0, 200.0),
        "disk_read_mb":          rng.uniform(20.0, 80.0),
        "disk_write_mb":         rng.uniform(10.0, 40.0),
        "inbound_mb":            rng.uniform(2.0, 8.0),
        "outbound_mb":           rng.uniform(0.5, 2.0),
        "external_packet_count": rng.randint(50, 250),
    }


def _make_segments() -> List[Tuple[str, dict]]:
    """[(scenario_label, segment_dict), ...] — 결정적 seed."""
    rng = random.Random(SEED)
    out = []
    for scn in SCENARIOS:
        for k in range(PER_SCENARIO):
            snaps = [_gen_snapshot(scn, rng, i) for i in range(WINDOW)]
            seg = {
                "segment_id": f"{scn}-{k}",
                "pc_id": f"{scn}-{k}",
                "slot": "class",
                "start_ts": snaps[0]["timestamp"],
                "end_ts": snaps[-1]["timestamp"],
                "window_size": WINDOW,
                "snapshots": snaps,
            }
            out.append((scn, seg))
    return out


def _reload_modules():
    """env 변경 후 segment_embedding / retrieval_store 의 모듈 상수를 새로고침."""
    from ml_server.retrieval import segment_embedding, retrieval_store
    importlib.reload(segment_embedding)
    importlib.reload(retrieval_store)
    return segment_embedding, retrieval_store


def _evaluate(mode: str, normalize: bool) -> Dict:
    """mode in ('euclidean','cosine'), normalize True/False."""
    os.environ["RETRIEVAL_DISTANCE_MODE"] = mode
    os.environ["RETRIEVAL_NORMALIZE"] = "1" if normalize else "0"
    SE, RS = _reload_modules()
    RS.reset_store()

    items = _make_segments()
    # 1. 적재 (verdict = 시나리오 자체)
    for label, seg in items:
        emb = SE.build_embedding(seg)
        RS.add_segment(seg, emb, verdict=label.upper(), score=0.0)

    # 2. 각 segment 를 쿼리로 사용 (self exclude).
    same_distances: List[float] = []
    other_distances: List[float] = []
    recall_hits = 0
    precision_sum = 0.0
    total_queries = 0
    confusion: Dict[str, Dict[str, int]] = {
        s: {t: 0 for t in SCENARIOS} for s in SCENARIOS
    }

    K = 5
    # separability 는 모든 segment 쌍에 대해 측정 (top-K 와 별도)
    embeddings: List[Tuple[str, List[float]]] = []
    for label, seg in items:
        embeddings.append((label, SE.build_embedding(seg)))

    dist_fn = RS._cosine_distance if mode == "cosine" else RS._euclidean
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            li, ei = embeddings[i]
            lj, ej = embeddings[j]
            d = dist_fn(ei, ej)
            if li == lj:
                same_distances.append(d)
            else:
                other_distances.append(d)

    # Recall/Precision: top-K 검색 결과로 측정
    for qlabel, qseg in items:
        qemb = SE.build_embedding(qseg)
        results = RS.search_similar(qseg, qemb, top_k=K)
        if not results:
            continue
        total_queries += 1
        topk_labels = [r["verdict"].lower() for r in results]
        same_in_topk = sum(1 for lab in topk_labels if lab == qlabel)
        if same_in_topk > 0:
            recall_hits += 1
        precision_sum += same_in_topk / K
        for r in results:
            confusion[qlabel][r["verdict"].lower()] += 1

    recall = recall_hits / total_queries if total_queries else 0.0
    precision = precision_sum / total_queries if total_queries else 0.0
    avg_same = sum(same_distances) / len(same_distances) if same_distances else 0.0
    avg_other = sum(other_distances) / len(other_distances) if other_distances else 0.0
    # separability: other / same (높을수록 분리도 우수). same 0 방지.
    sep = avg_other / avg_same if avg_same > 1e-9 else float("inf")

    return {
        "mode":       mode,
        "normalize":  normalize,
        "queries":    total_queries,
        "recall@5":   recall,
        "precision@5": precision,
        "avg_same":   avg_same,
        "avg_other":  avg_other,
        "separability": sep,
        "confusion":  confusion,
    }


def _format_confusion(c: Dict[str, Dict[str, int]]) -> str:
    header = "| query \\ retrieved | normal | mining | training |"
    sep = "|---|---|---|---|"
    rows = [header, sep]
    for s in SCENARIOS:
        rows.append(
            f"| **{s}** | {c[s]['normal']} | {c[s]['mining']} | {c[s]['training']} |"
        )
    return "\n".join(rows)


def main():
    print("[eval] Euclidean (raw) ...")
    euc = _evaluate(mode="euclidean", normalize=False)
    print("[eval] Cosine (normalized) ...")
    cos = _evaluate(mode="cosine", normalize=True)

    # 콘솔 요약
    for r in (euc, cos):
        print(
            f"  {r['mode']:10s} norm={r['normalize']} "
            f"R@5={r['recall@5']:.3f} P@5={r['precision@5']:.3f} "
            f"avg_same={r['avg_same']:.4f} avg_other={r['avg_other']:.4f} "
            f"sep={r['separability']:.2f}x"
        )

    out_md = ROOT / "docs" / "retrieval_quality_report.md"
    lines = []
    lines.append("# Retrieval Quality Report (R2)")
    lines.append("")
    lines.append("RADA R2: per-feature 정규화 + cosine distance 도입 효과를 합성 데이터로 측정.")
    lines.append("")
    lines.append("## Setup")
    lines.append(f"- 합성 segment: {len(SCENARIOS) * PER_SCENARIO} 개 ({PER_SCENARIO} × {', '.join(SCENARIOS)})")
    lines.append(f"- window_size: {WINDOW} snapshots/segment")
    lines.append(f"- seed: {SEED} (deterministic)")
    lines.append(f"- 각 segment 를 쿼리로 사용하여 self-exclude self-search, top-K=5")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Mode | Normalize | Recall@5 | Precision@5 | avg dist (same) | avg dist (other) | Separability |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in (euc, cos):
        lines.append(
            f"| {r['mode']} | {r['normalize']} | "
            f"{r['recall@5']:.3f} | {r['precision@5']:.3f} | "
            f"{r['avg_same']:.4f} | {r['avg_other']:.4f} | "
            f"{r['separability']:.2f}x |"
        )
    lines.append("")
    lines.append("Separability = avg distance(other scenario) / avg distance(same scenario). 클수록 분리도 우수.")
    lines.append("")
    lines.append("## Confusion (top-5 verdict counts per query scenario)")
    lines.append("")
    lines.append("### Euclidean (raw)")
    lines.append("")
    lines.append(_format_confusion(euc["confusion"]))
    lines.append("")
    lines.append("### Cosine (normalized)")
    lines.append("")
    lines.append(_format_confusion(cos["confusion"]))
    lines.append("")
    lines.append("## Conclusion")
    lines.append("")
    if cos["recall@5"] >= euc["recall@5"] and cos["separability"] >= euc["separability"]:
        delta_s = cos["separability"] / max(euc["separability"], 1e-9)
        lines.append(
            f"- Recall@5: euclidean {euc['recall@5']:.3f} → cosine {cos['recall@5']:.3f} "
            f"(시나리오 회수 성능 유지)"
        )
        lines.append(
            f"- Precision@5: {euc['precision@5']:.3f} → {cos['precision@5']:.3f}"
        )
        lines.append(
            f"- Separability: **{euc['separability']:.2f}x → {cos['separability']:.2f}x "
            f"({delta_s:.2f}배 향상)** — same-scenario 와 other-scenario 의 평균 거리 "
            f"비율이 더 벌어졌다."
        )
        lines.append("")
        lines.append(
            "큰 스케일 feature (vram_mb, packet_count) 의 raw Euclidean 거리 dominance 가 "
            "log1p + min-max 정규화로 사라지고, cosine 이 방향(패턴) 중심 검색을 한 결과. "
            "또한 cosine 의 거리 범위가 [0, 2] 로 고정되어 score breakdown 의 임계값 "
            "(_NEAR_DISTANCE_COSINE=0.35) 을 도메인 무관하게 안정적으로 적용할 수 있다. "
            "운영 기본값으로 cosine + normalize 채택. 회귀 안전을 위해 "
            "`RETRIEVAL_DISTANCE_MODE=euclidean`, `RETRIEVAL_NORMALIZE=0` 으로 기존 동작 "
            "복원 가능."
        )
    else:
        lines.append(
            "Cosine 모드가 모든 지표에서 우위는 아니다 — 시나리오 별로 raw 통계 유지가 "
            "유리한 패턴이 있을 수 있다. RETRIEVAL_DISTANCE_MODE 로 전환 가능."
        )
    lines.append("")
    lines.append("## How to reproduce")
    lines.append("")
    lines.append("```bash")
    lines.append("python tools/retrieval_quality_eval.py")
    lines.append("```")
    lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[eval] wrote {out_md}")


if __name__ == "__main__":
    main()
