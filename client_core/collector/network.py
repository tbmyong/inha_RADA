"""네트워크 수집기 (5초 증분 + 외부 연결 필터)."""
from __future__ import annotations

import ipaddress
from typing import Dict, Iterable, Optional, Set

import psutil

from .base import BaseCollector


def is_internal_ip(ip: str) -> bool:
    """ipaddress.is_private 기반. 사설망(10/8, 172.16-31, 192.168/16 등)이면 True."""
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


class NetworkCollector(BaseCollector):
    """net_io_counters 증분 + 외부 연결 카운트.

    - 첫 호출은 이전 누적값이 없어 0을 리턴(워밍업).
    - 외부 IP & 비표준 포트만 의심 트래픽으로 카운트.
    """

    CAP = 10

    def __init__(self, normal_ports: Optional[Iterable[int]] = None) -> None:
        self._prev = None
        self.normal_ports: Set[int] = set(normal_ports or [])

    def collect(self) -> Dict:
        net = psutil.net_io_counters()
        if self._prev is None:
            inbound_delta = outbound_delta = 0.0
        else:
            inbound_delta = max(
                0.0, round((net.bytes_recv - self._prev.bytes_recv) / (1024 ** 2), 4)
            )
            outbound_delta = max(
                0.0, round((net.bytes_sent - self._prev.bytes_sent) / (1024 ** 2), 4)
            )
        self._prev = net

        external_connections_raw = []
        active_ports: Set[int] = set()
        unique_ips: Set[str] = set()
        unique_ports: Set[int] = set()
        unique_pids: Set[int] = set()
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr:
                    active_ports.add(conn.laddr.port)
                if conn.raddr and conn.raddr.ip:
                    rip = conn.raddr.ip
                    rport = conn.raddr.port
                    active_ports.add(rport)
                    if is_internal_ip(rip) or rport in self.normal_ports:
                        continue
                    pid = getattr(conn, "pid", None)
                    external_connections_raw.append(
                        {"ip": rip, "port": rport, "status": conn.status, "pid": pid}
                    )
                    unique_ips.add(rip)
                    unique_ports.add(rport)
                    if pid is not None:
                        unique_pids.add(pid)
        except Exception:
            pass

        raw_count = len(external_connections_raw)
        # 중복: (ip, port, pid) 3중쌍 동일 → 중복 1건
        seen_triples = set()
        duplicate_count = 0
        for c in external_connections_raw:
            key = (c["ip"], c["port"], c.get("pid"))
            if key in seen_triples:
                duplicate_count += 1
            else:
                seen_triples.add(key)

        # cap 적용된 응답 (기존 키 보존: external_connections 항목은 ip/port/status만)
        capped = [
            {"ip": c["ip"], "port": c["port"], "status": c["status"]}
            for c in external_connections_raw[: self.CAP]
        ]

        return {
            "inbound_delta_mb": inbound_delta,
            "outbound_delta_mb": outbound_delta,
            "inbound_total_mb": round(net.bytes_recv / (1024 ** 2), 2),
            "outbound_total_mb": round(net.bytes_sent / (1024 ** 2), 2),
            "external_connection_count": raw_count,
            "external_connections": capped,
            "active_ports": list(active_ports),
            "external_connection_count_raw": raw_count,
            "external_connection_count_truncated": raw_count > self.CAP,
            "unique_remote_ip_count": len(unique_ips),
            "unique_remote_port_count": len(unique_ports),
            "unique_remote_process_count": len(unique_pids),
            "duplicate_connection_count": duplicate_count,
        }
