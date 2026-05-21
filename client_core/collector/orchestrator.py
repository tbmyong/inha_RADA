"""Collector들을 묶어 통합 메트릭 dict를 생성.

ML 서버 페이로드 키 22개를 보존한다.
선택적으로 derived_features (13키) 를 추가한다 — 22키는 불변.
"""
from __future__ import annotations

import datetime
import time
from typing import Dict, Optional

from .. import __version__
from ..identity import PC_ID
from .cpu_mem import CpuMemCollector
from .disk import DiskCollector
from .gpu import GpuCollector
from .network import NetworkCollector
from .process import ProcessCollector


class CollectorOrchestrator:
    """5초마다 한 번 collect()를 호출.

    구성 가능: 각 sub-collector를 외부에서 주입할 수 있어 테스트 용이.
    """

    def __init__(
        self,
        pc_id: str = PC_ID,
        cpu_mem: Optional[CpuMemCollector] = None,
        gpu: Optional[GpuCollector] = None,
        network: Optional[NetworkCollector] = None,
        disk: Optional[DiskCollector] = None,
        process: Optional[ProcessCollector] = None,
        normal_ports=None,
        collection_interval_sec: int = 5,
    ) -> None:
        self.pc_id = pc_id
        self.cpu_mem = cpu_mem or CpuMemCollector()
        self.gpu = gpu or GpuCollector()
        self.network = network or NetworkCollector(normal_ports=normal_ports or [])
        self.disk = disk or DiskCollector()
        self.process = process or ProcessCollector()
        self.collection_interval_sec = collection_interval_sec

    def collect(self) -> Dict:
        loop_start = time.time()
        cpu_mem = self.cpu_mem.collect()
        network = self.network.collect()
        gpu_result = self.gpu.collect()
        # GpuCollector는 (dict|None, reason|None) 튜플 반환.
        # 하위 호환: dict 단일 반환도 허용.
        if isinstance(gpu_result, tuple):
            gpu, gpu_reason = gpu_result
        else:
            gpu, gpu_reason = gpu_result, None
        procs = self.process.collect()
        disk = self.disk.collect()

        metrics = {
            "pc_id": self.pc_id,
            # timezone-aware ISO-8601 with offset. Spring's MetricsRequest
            # binds this into OffsetDateTime, which rejects naive timestamps
            # (returns HTTP 500 + Jackson parse error). astimezone() with no
            # argument uses the host's local TZ, so the offset is whatever
            # the runtime is configured for (KST=+09:00 in our case).
            "timestamp": datetime.datetime.now().astimezone().isoformat(),
            "cpu_percent": cpu_mem["cpu_percent"],
            "cpu_core_count": cpu_mem["cpu_core_count"],
            "memory_percent": cpu_mem["memory_percent"],
            "memory_used_gb": cpu_mem["memory_used_gb"],
            "memory_total_gb": cpu_mem["memory_total_gb"],
            "disk_read_mb": disk["disk_read_mb"],
            "disk_write_mb": disk["disk_write_mb"],
            "inbound_mb": network["inbound_delta_mb"],
            "outbound_mb": network["outbound_delta_mb"],
            "inbound_total_mb": network["inbound_total_mb"],
            "outbound_total_mb": network["outbound_total_mb"],
            "external_packet_count": network["external_connection_count"],
            "external_connection_count": network["external_connection_count"],
            "external_connections": network["external_connections"],
            "active_ports": network["active_ports"],
            "gpu": gpu,
            "top_processes": procs,
            "loop_elapsed": round(time.time() - loop_start, 3),
        }

        # collector 단위 미수신 사유 (수집 실패 vs 실제 0/empty 구분).
        network_reason = network.get("network_collection_missing_reason")
        process_reason = getattr(self.process, "last_missing_reason", None)

        # user idle (cryptojacking 의 "사용자 inactive 인데 자원 풀가동" 패턴 잡기 위함).
        # Windows GetLastInputInfo. 다른 OS 는 missing_reason.
        try:
            from . import system_idle as _idle_mod
            idle_ms, idle_reason = _idle_mod.collect()
        except Exception as exc:  # pragma: no cover - defensive
            idle_ms, idle_reason = None, f"import_failed:{type(exc).__name__}"

        # derived_features — partial failure 도 허용. 가능한 키는 최대한 채우고,
        # 실패한 sub-block 만 missing_reason 으로 표시한다.
        derived: Dict = {
            "collector_version": __version__,
            "collection_interval_sec": self.collection_interval_sec,
            "gpu_metrics_missing_reason": gpu_reason,
            "network_collection_missing_reason": network_reason,
            "process_collection_missing_reason": process_reason,
            "user_idle_ms": idle_ms,
            "user_idle_collection_missing_reason": idle_reason,
        }
        derived_missing_reasons: Dict[str, str] = {}

        # cpu_mem block
        try:
            derived["logical_cpu_count"] = cpu_mem.get("logical_cpu_count", 0)
            derived["physical_cpu_count"] = cpu_mem.get("physical_cpu_count", 0)
            derived["uptime_sec"] = cpu_mem.get("uptime_sec", 0)
        except Exception as e:  # pragma: no cover - defensive
            derived_missing_reasons["cpu_mem"] = type(e).__name__

        # process-derived block
        try:
            top_norm = [
                p.get("cpu_percent_normalized", 0.0) for p in procs
            ]
            top_sum = round(sum(top_norm), 2) if top_norm else 0.0
            top_max = round(max(top_norm), 2) if top_norm else 0.0
            derived["top_process_cpu_sum_normalized"] = top_sum
            derived["top_process_cpu_max_normalized"] = top_max
        except Exception as e:  # pragma: no cover - defensive
            derived_missing_reasons["process_derived"] = type(e).__name__

        # network-derived block
        try:
            derived["external_connection_count_raw"] = network.get(
                "external_connection_count_raw",
                network.get("external_connection_count", 0),
            )
            derived["external_connection_count_truncated"] = network.get(
                "external_connection_count_truncated", False
            )
            derived["unique_remote_ip_count"] = network.get("unique_remote_ip_count", 0)
            derived["unique_remote_port_count"] = network.get("unique_remote_port_count", 0)
            derived["unique_remote_process_count"] = network.get(
                "unique_remote_process_count", 0
            )
            derived["duplicate_connection_count"] = network.get(
                "duplicate_connection_count", 0
            )
        except Exception as e:  # pragma: no cover - defensive
            derived_missing_reasons["network_derived"] = type(e).__name__

        if derived_missing_reasons:
            derived["derived_missing_reasons"] = derived_missing_reasons

        metrics["derived_features"] = derived
        return metrics
