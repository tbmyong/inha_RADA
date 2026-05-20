"""GPU NVML partial failure tracking — gpu_partial_failure_reasons."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import client_core.collector.gpu as gpu_mod
from client_core.collector.gpu import GpuCollector


def _fake_gpu_obj(temp=55.0):
    g = MagicMock()
    g.name = "FakeGPU"
    g.load = 0.42
    g.memoryUsed = 1024.0
    g.memoryTotal = 8192.0
    g.temperature = temp
    return g


def test_no_partial_failures_when_clean():
    if not gpu_mod.GPU_AVAILABLE:
        return
    with patch("client_core.collector.gpu.GPUtil.getGPUs", return_value=[_fake_gpu_obj()]):
        with patch.object(gpu_mod, "PYNVML_AVAILABLE", False):
            c = GpuCollector()
            data, reason = c.collect()
            assert reason is None
            assert data is not None
            # NVML 비활성 + GPUtil 성공 → partial reasons 없음.
            assert "gpu_partial_failure_reasons" not in data


def test_temperature_failure_recorded():
    if not gpu_mod.GPU_AVAILABLE:
        return
    bad = _fake_gpu_obj()
    type(bad).temperature = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("temp sensor failed"))
    )
    with patch("client_core.collector.gpu.GPUtil.getGPUs", return_value=[bad]):
        with patch.object(gpu_mod, "PYNVML_AVAILABLE", False):
            c = GpuCollector()
            data, reason = c.collect()
            assert data is not None
            assert data["temperature"] is None
            assert "gpu_partial_failure_reasons" in data
            assert "temp_read_failed" in data["gpu_partial_failure_reasons"]


def test_nvml_subfield_failures_accumulate():
    """sm_util/power/tensor 가 각각 실패하면 별도 reason 으로 누적."""
    if not gpu_mod.GPU_AVAILABLE:
        return
    fake_pynvml = MagicMock()
    fake_pynvml.nvmlDeviceGetHandleByIndex.return_value = object()
    fake_pynvml.nvmlDeviceGetUtilizationRates.side_effect = RuntimeError("sm fail")
    fake_pynvml.nvmlDeviceGetPowerUsage.side_effect = RuntimeError("power fail")
    fake_pynvml.nvmlDeviceGetFieldValues.side_effect = RuntimeError("tensor fail")
    fake_pynvml.NVML_FI_DEV_TENSOR_ACTIVE = 0

    with patch("client_core.collector.gpu.GPUtil.getGPUs", return_value=[_fake_gpu_obj()]):
        with patch.object(gpu_mod, "PYNVML_AVAILABLE", True):
            with patch.object(gpu_mod, "pynvml", fake_pynvml):
                c = GpuCollector()
                data, reason = c.collect()
                assert reason is None
                assert data is not None
                reasons = data.get("gpu_partial_failure_reasons", [])
                assert "sm_util_unavailable" in reasons
                assert "power_unavailable" in reasons
                assert "tensor_core_unavailable" in reasons
                # None 으로 잠그지 0 으로 잠그지 않음.
                assert data["sm_utilization"] is None
                assert data["power_draw_w"] is None
                assert data["tensor_core_active"] is None


def test_nvml_handle_unavailable():
    if not gpu_mod.GPU_AVAILABLE:
        return
    fake_pynvml = MagicMock()
    fake_pynvml.nvmlDeviceGetHandleByIndex.side_effect = RuntimeError("no handle")
    with patch("client_core.collector.gpu.GPUtil.getGPUs", return_value=[_fake_gpu_obj()]):
        with patch.object(gpu_mod, "PYNVML_AVAILABLE", True):
            with patch.object(gpu_mod, "pynvml", fake_pynvml):
                c = GpuCollector()
                data, reason = c.collect()
                assert reason is None
                assert data is not None
                assert "nvml_handle_unavailable" in data.get(
                    "gpu_partial_failure_reasons", []
                )


def test_signal_extractor_passes_through_partial_reasons():
    """gpu_partial_failure_reasons 가 signals_missing 에 'gpu_partial' 로 표시."""
    from collections import deque

    from ml_server.scorer.signal_extractor import extract_signals
    from ml_server.model.requests import MetricsRequest, GpuMetrics

    gm = GpuMetrics(
        name="X",
        load_percent=10.0,
        memory_used_mb=100.0,
        memory_total_mb=8000.0,
        memory_percent=1.25,
        temperature=50.0,
        sm_utilization=None,
        tensor_core_active=None,
        power_draw_w=None,
        gpu_partial_failure_reasons=["sm_util_unavailable"],
    )
    req = MetricsRequest(
        pc_id="pc-p", timestamp="2026-05-04T10:00:00",
        cpu_percent=5.0, memory_percent=10.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
        gpu=gm,
    )
    out = extract_signals(req, deque(), slot="class")
    assert "gpu_partial" in out.get("signals_missing", [])
    assert "sm_util_unavailable" in out.get("gpu_partial_failure_reasons", [])
