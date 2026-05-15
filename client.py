"""PC 자원 모니터링 클라이언트 (v9 — shim)

이 파일은 v9 모듈화 이후 얇은 호환성 레이어로 축소되었다.
실제 로직은 ``client_core`` 패키지에 분산되어 있다.

기존 함수 시그니처(legacy import 호환):
    PC_ID, INTERVAL, ML_SERVER_URL,
    LOCAL_WINDOW_SIZE, HW_BASELINE_WINDOW,
    THRESHOLDS, ABSOLUTE_THRESHOLDS, HW_DEGRADATION_RATIO,
    NORMAL_PORTS, GPU_AVAILABLE, PYNVML_AVAILABLE,
    is_internal_ip(), get_time_slot(),
    collect_metrics(), collect_network_metrics(),
    collect_gpu_metrics(), collect_processes(),
    detect_local_alerts(), detect_absolute_breach(),
    detect_hardware_degradation(), compute_boxplot_signal(),
    sanitize_for_json(), send_to_ml_server(),
    print_metrics(), main()

새 코드는 ``from client_core.runtime import ClientRuntime``을 권장.
"""
from __future__ import annotations

from client_core.collector import GPU_AVAILABLE, PYNVML_AVAILABLE
from client_core.collector.network import is_internal_ip
from client_core.config import defaults as _defaults
from client_core.detector import (
    AbsoluteBreachDetector,
    BoxplotDetector,
    HwDegradationDetector,
    ThresholdDetector,
)
from client_core.identity import PC_ID
from client_core.runtime import ClientRuntime
from client_core.sender import LocalQueue, MetricsSender, sanitize_for_json
from client_core.timeslot import get_time_slot
from client_core.window import SlidingWindow

# ── 레거시 상수 재노출 ──
INTERVAL = _defaults.INTERVAL
ML_SERVER_URL = _defaults.ML_SERVER_URL
LOCAL_WINDOW_SIZE = _defaults.LOCAL_WINDOW_SIZE
HW_BASELINE_WINDOW = _defaults.HW_BASELINE_WINDOW
THRESHOLDS = _defaults.THRESHOLDS
ABSOLUTE_THRESHOLDS = _defaults.ABSOLUTE_THRESHOLDS
HW_DEGRADATION_RATIO = _defaults.HW_DEGRADATION_RATIO
NORMAL_PORTS = _defaults.NORMAL_PORTS

# ── 레거시 모듈 전역 (싱글턴) ──
_runtime = ClientRuntime()
_local_window = _runtime.local_window
_hw_baseline = _runtime.hw_baseline


# ── 레거시 함수 시그니처 ──
def collect_network_metrics() -> dict:
    return _runtime.collector.network.collect()


def collect_gpu_metrics():
    return _runtime.collector.gpu.collect()


def collect_processes():
    return _runtime.collector.process.collect()


def collect_metrics() -> dict:
    return _runtime.collect_and_update_windows()


def detect_local_alerts(metrics: dict):
    return _runtime.threshold_det.detect(metrics)


def detect_absolute_breach(metrics: dict):
    return _runtime.absolute_det.detect(metrics)


def detect_hardware_degradation():
    return _runtime.hw_det.detect(_runtime.local_window, _runtime.hw_baseline)


def compute_boxplot_signal() -> dict:
    return _runtime.boxplot_det.compute(_runtime.local_window)


def send_to_ml_server(metrics: dict, local_alerts: list, boxplot_signal: dict):
    return _runtime.sender.send(metrics, local_alerts, boxplot_signal)


def print_metrics(metrics, local_alerts, hw_alerts, boxplot, server_result) -> None:
    _runtime._print(metrics, local_alerts, hw_alerts, boxplot, server_result)


def main() -> None:
    ClientRuntime().run_forever()


__all__ = [
    "PC_ID", "INTERVAL", "ML_SERVER_URL",
    "LOCAL_WINDOW_SIZE", "HW_BASELINE_WINDOW",
    "THRESHOLDS", "ABSOLUTE_THRESHOLDS", "HW_DEGRADATION_RATIO",
    "NORMAL_PORTS", "GPU_AVAILABLE", "PYNVML_AVAILABLE",
    "is_internal_ip", "get_time_slot",
    "collect_metrics", "collect_network_metrics",
    "collect_gpu_metrics", "collect_processes",
    "detect_local_alerts", "detect_absolute_breach",
    "detect_hardware_degradation", "compute_boxplot_signal",
    "sanitize_for_json", "send_to_ml_server",
    "print_metrics", "main",
    "ClientRuntime", "SlidingWindow", "LocalQueue", "MetricsSender",
    "ThresholdDetector", "AbsoluteBreachDetector",
    "BoxplotDetector", "HwDegradationDetector",
]


if __name__ == "__main__":
    main()
