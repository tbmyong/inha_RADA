"""GPU 수집기 (GPUtil + pynvml).

기존 agent.py의 collect_gpu_metrics() 로직을 그대로 모듈화.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from .base import BaseCollector

_INIT_REASON: Optional[str] = None

try:
    import GPUtil  # type: ignore
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    _INIT_REASON = "no_gputil"
except Exception:
    GPU_AVAILABLE = False
    _INIT_REASON = "unknown"

try:
    import pynvml  # type: ignore
    try:
        pynvml.nvmlInit()
        PYNVML_AVAILABLE = True
    except PermissionError:
        PYNVML_AVAILABLE = False
        if _INIT_REASON is None:
            _INIT_REASON = "permission_error"
    except Exception:
        PYNVML_AVAILABLE = False
        if _INIT_REASON is None:
            _INIT_REASON = "driver_error"
except ImportError:
    PYNVML_AVAILABLE = False
    if not GPU_AVAILABLE and _INIT_REASON is None:
        _INIT_REASON = "pynvml_error"
    elif _INIT_REASON is None and not GPU_AVAILABLE:
        _INIT_REASON = "pynvml_error"
except Exception:
    PYNVML_AVAILABLE = False
    if _INIT_REASON is None:
        _INIT_REASON = "unknown"


class GpuCollector(BaseCollector):
    """첫 번째 GPU의 부하/메모리/온도/전력/텐서코어 활성도 수집."""

    def collect(self) -> Tuple[Optional[Dict], Optional[str]]:
        if not GPU_AVAILABLE:
            # pynvml은 있고 GPUtil만 없을 수도 있음
            reason = _INIT_REASON or "no_gputil"
            return (None, reason)
        try:
            try:
                gpus = GPUtil.getGPUs()
            except PermissionError:
                return (None, "permission_error")
            except Exception:
                return (None, "driver_error")
            if not gpus:
                return (None, "no_gpu")
            gpu = gpus[0]
            result: Dict = {
                "name": gpu.name,
                "load_percent": round(gpu.load * 100, 1),
                "memory_used_mb": round(gpu.memoryUsed, 1),
                "memory_total_mb": round(gpu.memoryTotal, 1),
                "memory_percent": round(gpu.memoryUsed / gpu.memoryTotal * 100, 1),
                "temperature": gpu.temperature,
                "sm_utilization": None,
                "tensor_core_active": None,
                "power_draw_w": None,
            }
            if PYNVML_AVAILABLE:
                self._enrich_with_nvml(result)
            return (result, None)
        except PermissionError:
            return (None, "permission_error")
        except Exception:
            return (None, "unknown")

    @staticmethod
    def _enrich_with_nvml(result: Dict) -> None:
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            result["sm_utilization"] = util.gpu
            try:
                result["power_draw_w"] = round(
                    pynvml.nvmlDeviceGetPowerUsage(handle) / 1000, 1
                )
            except Exception:
                pass
            try:
                fields = [pynvml.NVML_FI_DEV_TENSOR_ACTIVE]
                values = pynvml.nvmlDeviceGetFieldValues(handle, fields)
                if values and values[0].nvmlReturn == 0:
                    result["tensor_core_active"] = values[0].value.uiVal
            except Exception:
                pass
        except Exception:
            pass
