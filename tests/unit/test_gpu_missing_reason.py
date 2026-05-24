"""GpuCollector missing reason 분류 검증."""
from __future__ import annotations

from unittest.mock import patch

import client_core.collector.gpu as gpu_mod
from client_core.collector.gpu import GpuCollector


def test_returns_tuple_type():
    """collect()는 (dict|None, str|None) 튜플을 반환한다."""
    c = GpuCollector()
    result = c.collect()
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_no_gputil_or_pynvml_returns_reason():
    """GPU_AVAILABLE 가 False면 None + 이유 문자열 반환."""
    with patch.object(gpu_mod, "GPU_AVAILABLE", False):
        c = GpuCollector()
        data, reason = c.collect()
        assert data is None
        assert reason in ("no_gputil", "pynvml_error", "driver_error", "unknown")


def test_no_gpu_when_empty_list():
    """GPUtil이 로드돼 있어도 getGPUs()가 빈 리스트면 'no_gpu'."""
    if not gpu_mod.GPU_AVAILABLE:
        # GPUtil 자체가 없는 환경 → 다른 경로로 검증 (위 테스트가 커버)
        return
    with patch("client_core.collector.gpu.GPUtil.getGPUs", return_value=[]):
        c = GpuCollector()
        data, reason = c.collect()
        assert data is None
        assert reason == "no_gpu"


def test_permission_error_classified():
    if not gpu_mod.GPU_AVAILABLE:
        return
    with patch(
        "client_core.collector.gpu.GPUtil.getGPUs",
        side_effect=PermissionError("denied"),
    ):
        c = GpuCollector()
        data, reason = c.collect()
        assert data is None
        assert reason == "permission_error"


def test_driver_error_classified():
    if not gpu_mod.GPU_AVAILABLE:
        return
    with patch(
        "client_core.collector.gpu.GPUtil.getGPUs",
        side_effect=RuntimeError("nvml fail"),
    ):
        c = GpuCollector()
        data, reason = c.collect()
        assert data is None
        assert reason == "driver_error"


def test_init_reason_module_cache_exists():
    """모듈 변수 _INIT_REASON 가 존재한다 (값은 환경 의존)."""
    assert hasattr(gpu_mod, "_INIT_REASON")
