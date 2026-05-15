"""통합 테스트용 합성 metrics 빌더.

- seed_history(pc_id, slot, n=60): numpy default_rng(42) 정상 분포 60건 시드
- normal_metrics / anomaly_metrics / context_metrics: 단건 페이로드 빌더
"""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

import numpy as np

# 시간표 슬롯별 시각: class=평일 10시, free=평일 22시
SLOT_HOUR: Dict[str, int] = {"class": 10, "free": 22}


def _ts(dt: datetime.datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _slot_dt(slot: str, idx: int = 0,
             base: Optional[datetime.datetime] = None) -> datetime.datetime:
    """주어진 slot에 해당하는 datetime을 반환 (idx초 가산)."""
    if base is None:
        # 평일(월요일) 고정
        base = datetime.datetime(2026, 5, 4, SLOT_HOUR.get(slot, 10), 0, 0)
    return base + datetime.timedelta(seconds=idx)


def normal_metrics(pc_id: str = "pc-int-1", slot: str = "class",
                   idx: int = 0, rng: Optional[np.random.Generator] = None) -> dict:
    """정상 분포 단건 (cpu~20, mem~40, gpu~10)."""
    if rng is None:
        rng = np.random.default_rng(42)
    cpu  = float(np.clip(rng.normal(20, 4), 0, 100))
    mem  = float(np.clip(rng.normal(40, 4), 0, 100))
    gpu  = float(np.clip(rng.normal(10, 3), 0, 100))
    vram = float(np.clip(rng.normal(800, 100), 0, 8192))
    return {
        "pc_id":                 pc_id,
        "timestamp":             _ts(_slot_dt(slot, idx)),
        "cpu_percent":           cpu,
        "cpu_core_count":        4,
        "memory_percent":        mem,
        "memory_used_gb":        4.0,
        "memory_total_gb":       16.0,
        "inbound_mb":            float(np.clip(rng.normal(0.05, 0.02), 0, 5)),
        "outbound_mb":           float(np.clip(rng.normal(0.03, 0.01), 0, 5)),
        "inbound_total_mb":      0.0,
        "outbound_total_mb":     0.0,
        "external_packet_count": int(np.clip(rng.normal(2, 1), 0, 6)),
        "external_connections":  [],
        "active_ports":          [80, 443],
        "disk_read_mb":          float(np.clip(rng.normal(0.5, 0.1), 0, 100)),
        "disk_write_mb":         float(np.clip(rng.normal(0.3, 0.1), 0, 100)),
        "gpu": {
            "name":            "GeForce RTX 3060",
            "load_percent":    gpu,
            "memory_used_mb":  vram,
            "memory_total_mb": 8192.0,
            "memory_percent":  vram / 8192.0 * 100,
            "temperature":     55.0,
            "sm_utilization":  gpu,
            "tensor_core_active": 0,
            "power_draw_w":    50.0,
        },
        "top_processes": [
            {"name": "chrome.exe", "cpu_percent": 5.0,
             "memory_percent": 8.0, "path": "C:\\Program Files\\Chrome\\chrome.exe"},
            {"name": "explorer.exe", "cpu_percent": 1.0,
             "memory_percent": 2.0, "path": "C:\\Windows\\explorer.exe"},
        ],
        "local_alerts":   [],
        "boxplot_signal": {},
    }


def anomaly_metrics(pc_id: str = "pc-int-1", slot: str = "class",
                    idx: int = 100, top_processes: Optional[List[dict]] = None) -> dict:
    """이상 입력: cpu 99 / 외부패킷 폭증 / 포트 다수."""
    payload = normal_metrics(pc_id=pc_id, slot=slot, idx=idx)
    payload["cpu_percent"]           = 99.0
    payload["memory_percent"]        = 92.0
    payload["external_packet_count"] = 80
    payload["inbound_mb"]            = 50.0
    payload["outbound_mb"]           = 25.0
    payload["active_ports"]          = list(range(40000, 40050))
    payload["external_connections"]  = [
        {"ip": f"203.0.113.{i}", "port": 4444 + i} for i in range(8)
    ]
    payload["disk_write_mb"] = 10.0
    payload["gpu"]["load_percent"]   = 95.0
    payload["gpu"]["memory_used_mb"] = 7000.0
    payload["gpu"]["sm_utilization"] = 95.0
    payload["gpu"]["power_draw_w"]   = 220.0
    payload["top_processes"]         = top_processes or [
        {"name": "suspicious.exe", "cpu_percent": 90.0,
         "memory_percent": 50.0, "path": "C:\\Temp\\suspicious.exe"},
    ]
    return payload


def context_metrics(kind: str = "game", pc_id: str = "pc-int-1",
                    slot: str = "class", idx: int = 100) -> dict:
    """동일 이상 + 게임/컴파일 컨텍스트 프로세스 추가."""
    if kind == "game":
        ctx_proc = {"name": "league of legends.exe", "cpu_percent": 30.0,
                    "memory_percent": 20.0,
                    "path": "C:\\Riot Games\\League of Legends\\League of Legends.exe"}
    elif kind == "compile":
        ctx_proc = {"name": "cl.exe", "cpu_percent": 50.0,
                    "memory_percent": 15.0,
                    "path": "C:\\msvc\\bin\\cl.exe"}
    else:
        raise ValueError(f"unknown kind: {kind}")
    base = anomaly_metrics(pc_id=pc_id, slot=slot, idx=idx)
    base["top_processes"] = [ctx_proc] + base["top_processes"]
    return base


def seed_history(client, pc_id: str = "pc-int-1", slot: str = "class",
                 n: int = 60) -> List[dict]:
    """TestClient로 정상 분포 n건을 /analyze에 주입.

    재학습 트리거(MIN_TRAIN_SIZE=60, RETRAIN_INTERVAL=60)를 만족시키도록
    n=60 이상이면 1차 학습이 완료된다.
    """
    rng = np.random.default_rng(42)
    responses: List[dict] = []
    for i in range(n):
        payload = normal_metrics(pc_id=pc_id, slot=slot, idx=i, rng=rng)
        r = client.post("/analyze", json=payload)
        assert r.status_code == 200, r.text
        responses.append(r.json())
    return responses
