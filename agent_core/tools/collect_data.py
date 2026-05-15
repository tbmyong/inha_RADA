"""PC monitoring metrics collector (CSV output, V3 schema-aligned).

This standalone tool is independent of the DB/ML pipeline. It writes a CSV row
per interval. Column names follow the V3 metrics schema (collected_at, inbound_mb,
outbound_mb, vram_mb) and include additional training-oriented columns plus a
derived feature-extractor block (physical/logical CPU counts, uptime, normalized
top-process CPU, external connection aggregates, GPU missing reason, ...).

Schema compatibility:
    The CSV header was extended from 27 to 39 columns. If an existing metrics.csv
    from an earlier version is present at the output path, its header will NOT
    match the current CSV_FIELDS list. Either:
      - Move/back it up (e.g. ``mv metrics.csv metrics.csv.bak``), or
      - Pass ``--output`` to a fresh path.
    Mixing old and new rows in a single file is not supported.
"""

import argparse
import csv
import ipaddress
import json
import logging
import socket
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    print("Error: 'psutil' 라이브러리가 필요합니다. 'pip install psutil'을 실행해주세요.")
    sys.exit(1)

try:
    from pynvml import (
        NVMLError,
        NVML_TEMPERATURE_GPU,
        nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetName,
        nvmlDeviceGetPowerUsage,
        nvmlDeviceGetTemperature,
        nvmlDeviceGetUtilizationRates,
        nvmlInit,
        nvmlShutdown,
    )

    HAS_NVML = True
except ImportError:
    HAS_NVML = False


INTERVAL_SECONDS = 5
COLLECTOR_VERSION = "1.0.0"
CSV_FIELDS = [
    # V3 mapped columns first
    "pc_id",
    "collected_at",
    "slot",
    "interval_seconds",
    "hostname",
    "cpu_percent",
    "cpu_logical_cores",
    "mem_percent",
    "mem_used_mb",
    "mem_total_mb",
    "disk_read_mb",
    "disk_write_mb",
    "inbound_mb",
    "outbound_mb",
    "gpu_percent",
    "vram_mb",
    # Training-oriented extras
    "gpu_available",
    "gpu_name",
    "gpu_sm_percent",
    "gpu_vram_total_mb",
    "gpu_temp_c",
    "gpu_power_w",
    "gpu_tensor_core_active",
    "external_connection_count",
    "external_connections_json",
    "process_count",
    "top_processes_json",
    # Derived feature-extractor block (added in v1.0.0)
    "physical_cpu_count",
    "logical_cpu_count",
    "collection_interval_sec",
    "uptime_sec",
    "collector_version",
    "top_process_cpu_sum_normalized",
    "top_process_cpu_max_normalized",
    "external_connection_count_raw",
    "external_connection_count_truncated",
    "unique_remote_ip_count",
    "unique_remote_port_count",
    "unique_remote_process_count",
    "duplicate_connection_count",
    "gpu_metrics_missing_reason",
]


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def fixed_pc_id() -> str:
    """Generate a stable PC id from the primary MAC address."""
    return f"pc-{uuid.getnode():012x}"


def current_slot(now: datetime) -> str:
    """class: weekdays 09:00-18:00, free: everything else."""
    if now.weekday() < 5 and 9 <= now.hour < 18:
        return "class"
    return "free"


def mb(value: float) -> float:
    return round(value / 1024 / 1024, 4)


def is_external_ip(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


class GpuCollector:
    def __init__(self):
        self.available = False
        self.handle = None
        self.name = None
        self.total_mb = None
        self.missing_reason: str | None = None

        if not HAS_NVML:
            self.missing_reason = "pynvml_error"
            logger.info("pynvml이 없어 GPU 상세 지표는 null로 저장합니다.")
            return

        try:
            nvmlInit()
        except PermissionError:
            self.missing_reason = "permission_error"
            logger.warning("GPU nvmlInit 권한 오류")
            return
        except Exception as exc:
            self.missing_reason = "driver_error"
            logger.warning("GPU nvmlInit 실패: %s", exc)
            return

        try:
            self.handle = nvmlDeviceGetHandleByIndex(0)
        except Exception as exc:
            self.missing_reason = "no_gpu"
            logger.warning("GPU 핸들 획득 실패: %s", exc)
            return

        try:
            raw_name = nvmlDeviceGetName(self.handle)
            self.name = raw_name.decode("utf-8", errors="replace") if isinstance(raw_name, bytes) else str(raw_name)
            self.total_mb = mb(nvmlDeviceGetMemoryInfo(self.handle).total)
            self.available = True
        except Exception as exc:
            self.missing_reason = "unknown"
            logger.warning("GPU 초기 메타데이터 수집 실패: %s", exc)

    def collect(self) -> dict:
        if not self.available or self.handle is None:
            return {
                "gpu_available": False,
                "gpu_name": None,
                "gpu_percent": None,
                "gpu_sm_percent": None,
                "vram_mb": None,
                "gpu_vram_total_mb": None,
                "gpu_temp_c": None,
                "gpu_power_w": None,
                "gpu_tensor_core_active": None,
                "gpu_metrics_missing_reason": self.missing_reason or "unknown",
            }

        data = {
            "gpu_available": True,
            "gpu_name": self.name,
            "gpu_percent": None,
            "gpu_sm_percent": None,
            "vram_mb": None,
            "gpu_vram_total_mb": self.total_mb,
            "gpu_temp_c": None,
            "gpu_power_w": None,
            "gpu_tensor_core_active": None,
            "gpu_metrics_missing_reason": None,
        }

        try:
            util = nvmlDeviceGetUtilizationRates(self.handle)
            data["gpu_percent"] = float(util.gpu)
            # NVML's GPU utilization is the closest portable proxy for SM utilization.
            data["gpu_sm_percent"] = float(util.gpu)
        except NVMLError:
            pass

        try:
            mem_info = nvmlDeviceGetMemoryInfo(self.handle)
            data["vram_mb"] = mb(mem_info.used)
            data["gpu_vram_total_mb"] = mb(mem_info.total)
        except NVMLError:
            pass

        try:
            data["gpu_power_w"] = round(nvmlDeviceGetPowerUsage(self.handle) / 1000, 3)
        except NVMLError:
            pass

        try:
            data["gpu_temp_c"] = float(nvmlDeviceGetTemperature(self.handle, NVML_TEMPERATURE_GPU))
        except NVMLError:
            pass

        # Tensor-core activity is not exposed consistently by pynvml across GPUs/drivers.
        # Keep the column for schema compatibility and store null when unsupported.
        return data

    def close(self):
        if HAS_NVML:
            try:
                nvmlShutdown()
            except Exception:
                pass


class CsvMetricsCollector:
    def __init__(self, output_path: Path, interval: int = INTERVAL_SECONDS, pc_id: str | None = None):
        self.output_path = output_path
        self.interval = interval
        self.pc_id = pc_id or fixed_pc_id()
        self.hostname = socket.gethostname()
        self.gpu = GpuCollector()
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        self.last_time = time.time()
        self.boot_time = psutil.boot_time()
        self.collector_version = COLLECTOR_VERSION
        self.physical_cpu = psutil.cpu_count(logical=False) or psutil.cpu_count(logical=True) or 1
        self.logical_cpu = psutil.cpu_count(logical=True) or 1
        self.prime_process_cpu()

    def collect(self) -> dict:
        now_time = time.time()
        elapsed = max(now_time - self.last_time, 0.001)
        now = datetime.now()

        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()

        row = {
            "pc_id": self.pc_id,
            "hostname": self.hostname,
            "collected_at": now.isoformat(timespec="seconds"),
            "slot": current_slot(now),
            "interval_seconds": round(elapsed, 3),
            "cpu_percent": cpu_percent,
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "mem_percent": mem.percent,
            "mem_used_mb": mb(mem.used),
            "mem_total_mb": mb(mem.total),
            "inbound_mb": mb(max(0, net.bytes_recv - self.last_net.bytes_recv)),
            "outbound_mb": mb(max(0, net.bytes_sent - self.last_net.bytes_sent)),
            "disk_read_mb": mb(max(0, disk.read_bytes - self.last_disk.read_bytes)),
            "disk_write_mb": mb(max(0, disk.write_bytes - self.last_disk.write_bytes)),
        }

        row.update(self.gpu.collect())

        external_connections = self.collect_external_connections()
        row["external_connection_count"] = len(external_connections)
        row["external_connections_json"] = json.dumps(external_connections, ensure_ascii=False, separators=(",", ":"))

        top_processes = self.collect_top_processes()
        row["process_count"] = len(psutil.pids())
        row["top_processes_json"] = json.dumps(top_processes, ensure_ascii=False, separators=(",", ":"))

        # Derived feature-extractor block (v1.0.0).
        row["physical_cpu_count"] = self.physical_cpu
        row["logical_cpu_count"] = self.logical_cpu
        row["collection_interval_sec"] = round(elapsed, 3)
        row["uptime_sec"] = round(now_time - self.boot_time, 1)
        row["collector_version"] = self.collector_version

        cpu_values = [float(p.get("cpu_percent") or 0) for p in top_processes]
        cpu_sum = sum(cpu_values)
        cpu_max = max(cpu_values) if cpu_values else 0.0
        denom = self.logical_cpu if self.logical_cpu else 1
        row["top_process_cpu_sum_normalized"] = round(cpu_sum / denom, 3)
        row["top_process_cpu_max_normalized"] = round(cpu_max / denom, 3)

        conn_stats = self._analyze_external_connections(external_connections, limit=50)
        row["external_connection_count_raw"] = conn_stats["raw_count"]
        row["external_connection_count_truncated"] = conn_stats["truncated"]
        row["unique_remote_ip_count"] = conn_stats["unique_remote_ip_count"]
        row["unique_remote_port_count"] = conn_stats["unique_remote_port_count"]
        row["unique_remote_process_count"] = conn_stats["unique_remote_process_count"]
        row["duplicate_connection_count"] = conn_stats["duplicate_connection_count"]

        self.last_net = net
        self.last_disk = disk
        self.last_time = now_time
        return row

    @staticmethod
    def _analyze_external_connections(connections: list[dict], limit: int = 50) -> dict:
        """Aggregate dedup/truncation stats from the captured external connection list."""
        raw_count = len(connections)
        truncated = raw_count >= limit
        unique_ips: set = set()
        unique_ports: set = set()
        unique_pids: set = set()
        triples: list = []
        for c in connections:
            ip = c.get("remote_ip")
            port = c.get("remote_port")
            pid = c.get("pid")
            if ip is not None:
                unique_ips.add(ip)
            if port is not None:
                unique_ports.add(port)
            if pid is not None:
                unique_pids.add(pid)
            triples.append((ip, port, pid))
        duplicate = len(triples) - len(set(triples))
        return {
            "raw_count": raw_count,
            "truncated": truncated,
            "unique_remote_ip_count": len(unique_ips),
            "unique_remote_port_count": len(unique_ports),
            "unique_remote_process_count": len(unique_pids),
            "duplicate_connection_count": max(0, duplicate),
        }

    def collect_external_connections(self, limit: int = 50) -> list[dict]:
        """Collect external connection candidates without classifying ports or attack types."""
        results = []
        try:
            connections = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, OSError):
            return results

        for conn in connections:
            if not conn.raddr:
                continue
            if conn.type == socket.SOCK_STREAM and conn.status != psutil.CONN_ESTABLISHED:
                continue

            remote_ip = getattr(conn.raddr, "ip", None)
            remote_port = getattr(conn.raddr, "port", None)
            if not remote_ip or not is_external_ip(remote_ip):
                continue

            proc_name = None
            proc_path = None
            if conn.pid:
                try:
                    proc = psutil.Process(conn.pid)
                    proc_name = proc.name()
                    proc_path = proc.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    pass

            results.append(
                {
                    "pid": conn.pid,
                    "process_name": proc_name,
                    "process_path": proc_path,
                    "remote_ip": remote_ip,
                    "remote_port": remote_port,
                    "status": conn.status,
                }
            )
            if len(results) >= limit:
                break

        return results

    def prime_process_cpu(self):
        for proc in psutil.process_iter():
            try:
                proc.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue

    def collect_top_processes(self, limit: int = 10) -> list[dict]:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "memory_percent", "exe"]):
            try:
                info = proc.info
                if info.get("pid") == 0:
                    continue
                processes.append(
                    {
                        "pid": info.get("pid"),
                        "name": info.get("name"),
                        "cpu_percent": round(float(proc.cpu_percent(interval=None) or 0), 3),
                        "memory_percent": round(float(info.get("memory_percent") or 0), 3),
                        "path": info.get("exe"),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue

        processes.sort(key=lambda item: item["cpu_percent"], reverse=True)
        return processes[:limit]

    def append_csv(self, row: dict):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.output_path.exists()
        with self.output_path.open("a", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})

    def close(self):
        self.gpu.close()


def parse_args():
    default_output = Path(__file__).resolve().parent / "metrics.csv"
    parser = argparse.ArgumentParser(description="Collect PC monitoring metrics to CSV.")
    parser.add_argument("--output", type=Path, default=default_output, help="CSV output path")
    parser.add_argument("--interval", type=int, default=INTERVAL_SECONDS, help="collection interval seconds")
    parser.add_argument("--pc-id", default=None, help="override stable pc_id")
    parser.add_argument("--once", action="store_true", help="collect one row after priming counters")
    return parser.parse_args()


def main():
    args = parse_args()
    collector = CsvMetricsCollector(output_path=args.output, interval=args.interval, pc_id=args.pc_id)
    logger.info("CSV 수집 시작: output=%s interval=%ss pc_id=%s", args.output, args.interval, collector.pc_id)

    try:
        # Prime percent and delta counters so the first saved row is a true interval delta.
        psutil.cpu_percent(interval=None)
        time.sleep(args.interval)

        while True:
            row = collector.collect()
            collector.append_csv(row)
            logger.info(
                "저장 완료: CPU=%s%% GPU=%s%% IN=%sMB OUT=%sMB DISK_R=%sMB DISK_W=%sMB EXT_CONN=%s",
                row["cpu_percent"],
                row["gpu_percent"],
                row["inbound_mb"],
                row["outbound_mb"],
                row["disk_read_mb"],
                row["disk_write_mb"],
                row["external_connection_count"],
            )

            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("수집 중단")
    finally:
        collector.close()


if __name__ == "__main__":
    main()
