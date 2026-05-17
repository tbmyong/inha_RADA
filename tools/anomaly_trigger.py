"""Mining 시나리오 시뮬레이션 — 15회 연속 의심 페이로드 전송.

scoring v0.5.0 기준 점수 기대값:
- resource: CPU 95%+ sustained → +2~3
- process: 'xmrig.exe' 미허용 + 의심 경로 → +2~3
- network: 외부 연결 + mining 포트 (3333) → +1~2
- correlation: cpu+gpu+net_out 동시 → +2
- final: 합산 9~14 (SUSPICIOUS) 또는 14+ (HIGH_RISK)
"""
import time
from datetime import datetime, timezone, timedelta
import requests

URL = "http://localhost:8080/api/metrics"
API_KEY = "smoke-key"
PC_ID = "pc-smoke"
KST = timezone(timedelta(hours=9))
XMRIG_PATH = r"C:\Users\Public\xmrig.exe"
CHROME_PATH = r"C:\Program Files\Google\Chrome\chrome.exe"


def mining_payload(i):
    return {
        "pc_id": PC_ID,
        "timestamp": datetime.now(KST).isoformat(),
        "cpu_percent": 96.0 + (i % 3),
        "cpu_core_count": 8,
        "memory_percent": 82.0,
        "memory_used_gb": 13.1,
        "memory_total_gb": 16.0,
        "disk_read_mb": 8.0,
        "disk_write_mb": 5.0,
        "inbound_mb": 0.5,
        "outbound_mb": 12.0,
        "inbound_total_mb": 100.0,
        "outbound_total_mb": 500.0 + i * 12,
        "external_packet_count": 1200 + i * 50,
        "external_connection_count": 4,
        "external_connections": [
            {"pid": 6666, "process_name": "xmrig.exe", "process_path": XMRIG_PATH,
             "remote_ip": "185.199.108.153", "remote_port": 3333, "status": "ESTABLISHED"},
            {"pid": 6666, "process_name": "xmrig.exe", "process_path": XMRIG_PATH,
             "remote_ip": "104.21.66.207", "remote_port": 7777, "status": "ESTABLISHED"},
        ],
        "active_ports": [3333, 7777],
        # gpu: ML 서버 GpuMetrics 스키마 일치 (name/load_percent/memory_*)
        "gpu": {
            "name": "NVIDIA GeForce RTX 3060",
            "load_percent": 95.0 + (i % 5),
            "memory_used_mb": 7800.0,
            "memory_total_mb": 12288.0,
            "memory_percent": 63.5,
            "temperature": 78.0 + (i % 4),
            "sm_utilization": 95,
            "tensor_core_active": None,
            "power_draw_w": 165.0,
        },
        "top_processes": [
            {"pid": 6666, "name": "xmrig.exe", "cpu_percent": 92.0,
             "memory_percent": 5.2, "path": XMRIG_PATH},
            {"pid": 1234, "name": "chrome.exe", "cpu_percent": 2.0,
             "memory_percent": 12.0, "path": CHROME_PATH},
        ],
        "loop_elapsed": 4.8,
        "local_alerts": [
            {"type": "cpu_sustained_high", "level": "warn", "value": 96.0},
            {"type": "unknown_process_active", "level": "warn", "process": "xmrig.exe"},
        ],
        "boxplot_signal": {"cpu_outlier": True, "outbound_outlier": True},
        "derived_features": {
            "logical_cpu_count": 8, "physical_cpu_count": 4,
            "uptime_sec": 86400, "collector_version": "1.0.0",
            "collection_interval_sec": 5,
            "top_process_cpu_sum_normalized": 0.94,
            "top_process_cpu_max_normalized": 0.92,
            "external_connection_count_raw": 4,
            "external_connection_count_truncated": False,
            "unique_remote_ip_count": 2,
            "unique_remote_port_count": 2,
            "unique_remote_process_count": 1,
            "duplicate_connection_count": 0,
            "gpu_metrics_missing_reason": None,
        },
    }


def main():
    sent = errs = 0
    for i in range(15):
        p = mining_payload(i)
        try:
            r = requests.post(URL, json=p,
                              headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
                              timeout=5)
            if r.status_code in (200, 202):
                sent += 1
                print(f"[{i+1:2}/15] OK {r.status_code} cpu={p['cpu_percent']:.1f}% "
                      f"gpu={p['gpu']['load_percent']:.1f}% out={p['outbound_mb']:.1f}MB")
            else:
                errs += 1
                print(f"[{i+1:2}/15] ERR {r.status_code} {r.text[:200]}")
        except Exception as e:
            errs += 1
            print(f"[{i+1:2}/15] EXC {e}")
        time.sleep(2)
    print(f"\nDone: sent={sent} errs={errs}")


if __name__ == "__main__":
    main()
