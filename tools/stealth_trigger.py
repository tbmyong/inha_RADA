"""Stealth mining 시뮬 — fast-path 신호 (known_miner / mining_pool_ip /
mining_port) 모두 회피하고도 RADA 가 잡는지 검증.

회피:
- process name: `wuauclt_helper.exe` (MINING_PROCESSES 외)
- process path: `C:\\Users\\Public\\AppData\\Roaming\\Microsoft\\wuauclt_helper.exe`
  → `appdata_exec` 발화 (suspicious path 효과)
- remote IP: 52.231.140.10 / 13.107.42.14 (MINING_POOL_IPS prefix 외)
- remote port: 443 (mining port 3333/7777 회피)

기대 발화 신호 (fast-path 아님):
- cpu_high + cpu_flat (지속 95~98%)
- gpu_high + gpu_flat (지속 92~96%)
- net_external_high (external_packet_count >= 8)
- net_out_sustained / outbound_spike
- appdata_exec, unknown_process_active
- top_process_cpu_sum_normalized 0.93

기대 점수 (이론):
- gpu_mining: gpu_high(1) + gpu_flat(3) + net_external_high(1) = 5
- cpu_mining: cpu_high(1) + cpu_flat(3) = 4
- correlation: cpu+net_out_sustained(2) + appdata_exec+net_out_sustained(6)
             + unknown_process_active+net_out_sustained(5) = 13
- → final ≥ 12 → SUSPICIOUS 이상 기대
"""
import time
from datetime import datetime, timezone, timedelta
import os
import requests

URL = os.environ.get("RADA_TRIGGER_URL", "http://localhost:8080/api/metrics")
API_KEY = os.environ.get("RADA_TRIGGER_API_KEY", "smoke-key")
PC_ID = os.environ.get("RADA_TRIGGER_PC_ID", "pc-stealth")
KST = timezone(timedelta(hours=9))

# AppData\Roaming 경로 — temp 아니지만 appdata_exec 트리거
STEALTH_PATH = r"C:\Users\Public\AppData\Roaming\Microsoft\wuauclt_helper.exe"
CHROME_PATH = r"C:\Program Files\Google\Chrome\chrome.exe"


def stealth_payload(i):
    return {
        "pc_id": PC_ID,
        "timestamp": datetime.now(KST).isoformat(),
        "cpu_percent": 95.0 + (i % 4) * 0.5,   # flat-high
        "cpu_core_count": 8,
        "memory_percent": 71.0,
        "memory_used_gb": 11.4,
        "memory_total_gb": 16.0,
        "disk_read_mb": 6.0,
        "disk_write_mb": 4.0,                  # disk_write_net_out_sustained 후보
        "inbound_mb": 0.3,
        "outbound_mb": 8.0 + (i % 3) * 0.2,    # sustained outbound
        "inbound_total_mb": 60.0,
        "outbound_total_mb": 300.0 + i * 8,
        "external_packet_count": 800 + i * 30,
        "external_connection_count": 3,
        "external_connections": [
            # mining pool prefix 가 아닌 IP (Azure / CloudFlare 대역)
            {"pid": 7777, "process_name": "wuauclt_helper.exe", "process_path": STEALTH_PATH,
             "remote_ip": "52.231.140.10", "remote_port": 443, "status": "ESTABLISHED"},
            {"pid": 7777, "process_name": "wuauclt_helper.exe", "process_path": STEALTH_PATH,
             "remote_ip": "13.107.42.14", "remote_port": 443, "status": "ESTABLISHED"},
        ],
        "active_ports": [443],                 # 3333/7777 회피
        "gpu": {
            "name": "NVIDIA GeForce RTX 3060",
            "load_percent": 93.0 + (i % 3) * 0.5,   # flat-high
            "memory_used_mb": 6200.0,
            "memory_total_mb": 12288.0,
            "memory_percent": 50.4,
            "temperature": 74.0 + (i % 3),
            "sm_utilization": 92,
            "tensor_core_active": None,
            "power_draw_w": 158.0,
        },
        "top_processes": [
            {"pid": 7777, "name": "wuauclt_helper.exe",      # ← MINING_PROCESSES 외
             "cpu_percent": 91.0, "memory_percent": 5.0, "path": STEALTH_PATH},
            {"pid": 1234, "name": "chrome.exe", "cpu_percent": 1.5,
             "memory_percent": 12.0, "path": CHROME_PATH},
        ],
        "loop_elapsed": 4.9,
        "local_alerts": [
            {"type": "cpu_sustained_high", "level": "warn", "value": 95.5},
            {"type": "unknown_process_active", "level": "warn", "process": "wuauclt_helper.exe"},
        ],
        "boxplot_signal": {"cpu_outlier": True, "outbound_outlier": True},
        "derived_features": {
            "logical_cpu_count": 8, "physical_cpu_count": 4,
            "uptime_sec": 86400, "collector_version": "1.0.0",
            "collection_interval_sec": 5,
            "top_process_cpu_sum_normalized": 0.93,
            "top_process_cpu_max_normalized": 0.91,
            "external_connection_count_raw": 3,
            "external_connection_count_truncated": False,
            "unique_remote_ip_count": 2,
            "unique_remote_port_count": 1,
            "unique_remote_process_count": 1,
            "duplicate_connection_count": 0,
            "gpu_metrics_missing_reason": None,
        },
    }


def main():
    sent = errs = 0
    for i in range(15):
        p = stealth_payload(i)
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
