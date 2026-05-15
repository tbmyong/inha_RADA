"""디스크 I/O 수집기 (5초 증분)."""
from __future__ import annotations

from typing import Dict

import psutil

from .base import BaseCollector


class DiskCollector(BaseCollector):
    """psutil.disk_io_counters의 누적값을 증분(MB/5s)으로 변환.

    누적값을 그대로 ML로 보내면 PC 가동 시간을 학습하게 되어 위험.
    """

    def __init__(self) -> None:
        self._prev = None

    def collect(self) -> Dict:
        disk = psutil.disk_io_counters()
        if self._prev is None:
            read_delta = 0.0
            write_delta = 0.0
        else:
            read_delta = max(
                0.0, round((disk.read_bytes - self._prev.read_bytes) / (1024 ** 2), 4)
            )
            write_delta = max(
                0.0, round((disk.write_bytes - self._prev.write_bytes) / (1024 ** 2), 4)
            )
        self._prev = disk
        return {
            "disk_read_mb": read_delta,
            "disk_write_mb": write_delta,
        }
