"""피처 엔지니어링 — 10차원(raw 7 + derived 3)."""
from typing import Optional
from ..model.requests import MetricsRequest


def build_features(
    cpu: float, memory: float,
    gpu_pct: float, vram_mb: float, gpu_total_mb: float,
    disk_r: float, disk_w: float, power: float,
) -> list:
    """
    ML 피처 (네트워크 제외).

    raw=[cpu, memory, gpu_pct, vram_mb, disk_r, disk_w, power] (7)
    derived=[cpu/(gpu+0.001), gpu-cpu, gpu*(1-vram/total)]    (3)
    합계 10차원.
    """
    raw = [cpu, memory, gpu_pct, vram_mb, disk_r, disk_w, power]
    gpu_total_safe = gpu_total_mb if gpu_total_mb > 0 else 8192
    derived = [
        cpu / (gpu_pct + 0.001),                   # 분모 0 방지
        gpu_pct - cpu,
        gpu_pct * (1 - vram_mb / gpu_total_safe),
    ]
    return raw + derived


def extract_features_from_snapshot(snap: dict) -> Optional[list]:
    try:
        return build_features(
            cpu=snap.get("cpu_percent", 0),
            memory=snap.get("memory_percent", 0),
            gpu_pct=snap.get("gpu_percent", 0) or 0,
            vram_mb=snap.get("gpu_vram_mb", 0) or 0,
            gpu_total_mb=snap.get("gpu_total_mb", 8192) or 8192,
            disk_r=snap.get("disk_read_mb", 0),
            disk_w=snap.get("disk_write_mb", 0),
            power=snap.get("gpu_power_w", 0) or 0,
        )
    except Exception:
        return None


def extract_features_from_metrics(metrics: MetricsRequest) -> list:
    gpu_total = metrics.gpu.memory_total_mb if metrics.gpu else 8192
    return build_features(
        cpu=metrics.cpu_percent,
        memory=metrics.memory_percent,
        gpu_pct=metrics.gpu.load_percent if metrics.gpu else 0,
        vram_mb=metrics.gpu.memory_used_mb if metrics.gpu else 0,
        gpu_total_mb=gpu_total,
        disk_r=metrics.disk_read_mb,
        disk_w=metrics.disk_write_mb,
        power=metrics.gpu.power_draw_w if metrics.gpu and metrics.gpu.power_draw_w else 0,
    )


def make_snapshot(metrics: MetricsRequest) -> dict:
    return {
        "timestamp":             metrics.timestamp,
        "cpu_percent":           metrics.cpu_percent,
        "memory_percent":        metrics.memory_percent,
        "gpu_percent":           metrics.gpu.load_percent      if metrics.gpu else None,
        "gpu_vram_mb":           metrics.gpu.memory_used_mb    if metrics.gpu else None,
        "gpu_total_mb":          metrics.gpu.memory_total_mb   if metrics.gpu else 8192,
        "gpu_power_w":           metrics.gpu.power_draw_w      if metrics.gpu else None,
        "tensor_core_active":    metrics.gpu.tensor_core_active if metrics.gpu else None,
        "inbound_mb":            metrics.inbound_mb,
        "outbound_mb":           metrics.outbound_mb,
        "external_packet_count": metrics.external_packet_count,
        "disk_read_mb":          metrics.disk_read_mb,
        "disk_write_mb":         metrics.disk_write_mb,
        "top_processes":         metrics.top_processes,
    }
