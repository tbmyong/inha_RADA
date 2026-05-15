"""프로세스 수집기. CPU 사용률 상위 10개."""
from __future__ import annotations

from typing import List

import psutil

from .base import BaseCollector


class ProcessCollector(BaseCollector):
    def __init__(self, top_n: int = 10) -> None:
        self.top_n = top_n
        try:
            self._logical_cpu = psutil.cpu_count(logical=True) or 1
        except Exception:
            self._logical_cpu = 1
        if self._logical_cpu <= 0:
            self._logical_cpu = 1

    def collect(self) -> List[dict]:
        try:
            pid_name_map = {}
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    pid_name_map[proc.info["pid"]] = proc.info["name"] or ""
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            proc_list = []
            for proc in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent", "exe", "status", "ppid"]
            ):
                try:
                    ppid = proc.info.get("ppid") or 0
                    cpu_raw = proc.info["cpu_percent"] or 0.0
                    proc_list.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"] or "",
                            "cpu_percent": cpu_raw,
                            "cpu_percent_normalized": round(
                                cpu_raw / self._logical_cpu, 2
                            ),
                            "memory_percent": round(
                                proc.info["memory_percent"] or 0.0, 2
                            ),
                            "path": proc.info["exe"] or "",
                            "status": proc.info["status"] or "",
                            "ppid": ppid,
                            "parent_name": pid_name_map.get(ppid, ""),
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            proc_list.sort(key=lambda p: p["cpu_percent"], reverse=True)
            return proc_list[: self.top_n]
        except Exception:
            return []
