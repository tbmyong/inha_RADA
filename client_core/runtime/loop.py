"""클라이언트 메인 루프 오케스트레이션.

기존 agent.py main()의 로직을 클래스로 재배치.
- collector → window 갱신 → detector → sender → print 순.
- 알고리즘 변경 없음.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

RETRY_PER_CYCLE = 5

from ..collector import CollectorOrchestrator, GPU_AVAILABLE, PYNVML_AVAILABLE
from ..config.loader import ClientConfig, load_config
from ..detector import (
    AbsoluteBreachDetector,
    BoxplotDetector,
    HwDegradationDetector,
    ThresholdDetector,
)
from ..identity import PC_ID
from ..sender import LocalQueue, MetricsSender
from ..timeslot import get_time_slot
from ..window import SlidingWindow


class ClientRuntime:
    def __init__(self, config: Optional[ClientConfig] = None) -> None:
        self.config = config or load_config(autodiscover=True)

        self.collector = CollectorOrchestrator(
            pc_id=PC_ID,
            normal_ports=self.config.normal_ports,
        )
        self.local_window = SlidingWindow(self.config.local_window_size)
        self.hw_baseline = SlidingWindow(self.config.hw_baseline_window)

        self.threshold_det = ThresholdDetector(self.config.thresholds)
        self.absolute_det = AbsoluteBreachDetector(self.config.absolute_thresholds)
        self.boxplot_det = BoxplotDetector(min_window=12)
        self.hw_det = HwDegradationDetector(
            local_window_size=self.config.local_window_size,
            hw_baseline_window=self.config.hw_baseline_window,
            ratio=self.config.hw_degradation_ratio,
        )

        self.queue = LocalQueue(
            max_size=self.config.local_queue_max_size,
            queue_path=self.config.local_queue_path,
            max_bytes=self.config.local_queue_max_bytes,
            fsync=self.config.local_queue_fsync,
        )
        self.sender = MetricsSender(
            config=self.config, queue=self.queue
        )

    def collect_and_update_windows(self) -> dict:
        metrics = self.collector.collect()
        gpu = metrics.get("gpu")
        self.local_window.append({
            "cpu_percent": metrics["cpu_percent"],
            "memory_percent": metrics["memory_percent"],
            "gpu_percent": gpu["load_percent"] if gpu else None,
            "gpu_temp": gpu["temperature"] if gpu else None,
        })
        self.hw_baseline.append({
            "cpu_percent": metrics["cpu_percent"],
            "memory_percent": metrics["memory_percent"],
        })
        return metrics

    def step(self) -> dict:
        """1회 루프 실행: 메트릭 수집 + 탐지 + 전송.

        반환: {metrics, local_alerts, hw_alerts, boxplot, server_result}
        """
        metrics = self.collect_and_update_windows()
        local_alerts = self.threshold_det.detect(metrics)
        absolute_alerts = self.absolute_det.detect(metrics)
        hw_alerts = self.hw_det.detect(self.local_window, self.hw_baseline)
        boxplot_signal = self.boxplot_det.compute(self.local_window)

        # 실패 큐 자동 drain (비율 제한: RETRY_PER_CYCLE 건/사이클).
        # collect_and_update_windows() 이후, sender.send() 이전 위치.
        drained_count = 0
        for _ in range(RETRY_PER_CYCLE):
            item = self.queue.pop()
            if item is None:
                break
            ok = self.sender.replay(item)
            if not ok:
                self.queue.put(item)
                break
            drained_count += 1
        if drained_count > 0:
            log.info("drained %d queued payloads", drained_count)

        all_local = local_alerts + absolute_alerts + hw_alerts
        server_result = self.sender.send(metrics, all_local, boxplot_signal)

        self._print(metrics, local_alerts + absolute_alerts, hw_alerts, boxplot_signal, server_result)
        return {
            "metrics": metrics,
            "local_alerts": local_alerts + absolute_alerts,
            "hw_alerts": hw_alerts,
            "boxplot": boxplot_signal,
            "server_result": server_result,
        }

    def run_forever(self) -> None:
        self._banner()
        # 워밍업 (이전값 없는 첫 수집 버림)
        self.collector.collect()
        time.sleep(self.config.interval)
        while True:
            loop_start = time.time()
            self.step()
            elapsed = time.time() - loop_start
            time.sleep(max(0.0, self.config.interval - elapsed))

    # ────────────────────────── helpers
    def _banner(self) -> None:
        cfg = self.config
        print("=== PC 자원 모니터링 클라이언트 v9 (모듈화) ===")
        print(f"PC ID:       {PC_ID}")
        print(f"GPU:         {'OK NVIDIA (GPUtil)' if GPU_AVAILABLE else 'X 미지원'}")
        print(f"pynvml:      {'OK' if PYNVML_AVAILABLE else 'X'}")
        print(f"ML 서버:     {cfg.ml_server_url}")
        print(f"수집 주기:   {cfg.interval}초")
        print(f"로컬 윈도우: {cfg.local_window_size}건 ({cfg.local_window_size * cfg.interval // 60}분)")
        print(f"기저선 윈도우:{cfg.hw_baseline_window}건 ({cfg.hw_baseline_window * cfg.interval // 60}분)")
        print()

    def _print(self, metrics, local_alerts, hw_alerts, boxplot, server_result) -> None:
        gpu = metrics.get("gpu")
        print(f"[{metrics['timestamp']}] PC: {metrics['pc_id']}  슬롯: {get_time_slot()}")
        print(
            f"  CPU:    {metrics['cpu_percent']}%  |  "
            f"Memory: {metrics['memory_percent']}% "
            f"({metrics['memory_used_gb']}GB / {metrics['memory_total_gb']}GB)"
        )
        if gpu:
            sm = f"  SM:{gpu['sm_utilization']}%" if gpu["sm_utilization"] is not None else ""
            tc = f"  텐서:{gpu['tensor_core_active']}%" if gpu["tensor_core_active"] is not None else ""
            pw = f"  {gpu['power_draw_w']}W" if gpu["power_draw_w"] is not None else ""
            print(
                f"  GPU:    {gpu['load_percent']}%{sm}{tc}{pw}  |  "
                f"VRAM:{gpu['memory_used_mb']}MB/{gpu['memory_total_mb']}MB  온도:{gpu['temperature']}°C"
            )
        else:
            print("  GPU:    미지원")
        print(
            f"  Net:    ↑{metrics['outbound_mb']}MB/5s  ↓{metrics['inbound_mb']}MB/5s  "
            f"외부:{metrics['external_packet_count']}건"
        )
        print(f"  Disk:   R:{metrics['disk_read_mb']}MB  W:{metrics['disk_write_mb']}MB")
        print(f"  프로세스: {[p['name'] for p in metrics['top_processes'][:5]]}")

        if boxplot.get("available"):
            flags = []
            if boxplot["cpu_iqr_outlier"]:
                flags.append(f"CPU이상(deviation={boxplot['cpu_deviation']})")
            if boxplot["mem_iqr_outlier"]:
                flags.append(f"MEM이상(deviation={boxplot['mem_deviation']})")
            print(
                f"  BoxPlot: {' '.join(flags) if flags else '정상범위'}  "
                f"[CPU Q1={boxplot['cpu_q1']} Q3={boxplot['cpu_q3']}  "
                f"MEM Q1={boxplot['mem_q1']} Q3={boxplot['mem_q3']}]"
            )

        all_local = local_alerts + hw_alerts
        if all_local:
            print("  [Layer1 규칙]")
            for a in all_local:
                icon = "[!]" if a["severity"] == "HIGH" else "[*]"
                print(f"    {icon} [{a['type']}] {a['detail']}")

        if server_result is not None:
            # springboot 모드는 202 Accepted + 빈 body (server_result == {})
            # mlserver 모드는 JSON 본문 (verdict / overall_severity) 포함
            if server_result and ("overall_severity" in server_result or "verdict" in server_result):
                sev = server_result.get("overall_severity", "ACK")
                verdict = server_result.get("verdict", "ACK")
                print(
                    f"  서버: {sev}  verdict={verdict}  "
                    f"(시간표:{server_result.get('timetable_slot','-')}  "
                    f"히스토리:{server_result.get('history_size',0)}건)"
                )
            else:
                print("  서버: 전송 OK (비동기 분석)")
            for alert in server_result.get("alerts", []):
                score = f" (점수:{alert.get('score','')})" if alert.get("score") else ""
                print(f"    └ [{alert['severity']}] {alert['detail']}{score}")
        else:
            print("  ML서버: 연결 없음 (로컬 판단만)")
        print()
