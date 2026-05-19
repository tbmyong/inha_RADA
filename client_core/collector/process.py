"""프로세스 수집기. CPU 사용률 상위 10개."""
from __future__ import annotations

from typing import List, Optional

import psutil

from .base import BaseCollector


class ProcessCollector(BaseCollector):
    def __init__(self, top_n: int = 10) -> None:
        self.top_n = top_n
        # 수집 실패와 실제 빈 리스트를 구분하기 위한 미수신 사유 (gpu.py 패턴과 동치).
        # 정상 시 None. 예외 발생 시 사유 문자열.
        self.last_missing_reason: Optional[str] = None
        try:
            self._logical_cpu = psutil.cpu_count(logical=True) or 1
        except Exception:
            self._logical_cpu = 1
        if self._logical_cpu <= 0:
            self._logical_cpu = 1

    def collect(self) -> List[dict]:
        self.last_missing_reason = None
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
        except PermissionError:
            self.last_missing_reason = "permission_error"
            return []
        except OSError:
            self.last_missing_reason = "os_error"
            return []
        except Exception:
            self.last_missing_reason = "unknown"
            return []
