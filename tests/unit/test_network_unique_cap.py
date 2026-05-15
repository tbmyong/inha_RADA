"""NetworkCollector unique/cap/duplicate 카운트 검증."""
from __future__ import annotations

from unittest.mock import patch

from agent_core.collector.network import NetworkCollector


class FakeAddr:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


class FakeConn:
    def __init__(self, laddr, raddr, status="ESTABLISHED", pid=None):
        self.laddr = laddr
        self.raddr = raddr
        self.status = status
        self.pid = pid


class FakeNetIO:
    bytes_recv = 0
    bytes_sent = 0


def _make_conns(n_external: int, unique_ips: int = None, unique_ports: int = None):
    """외부 연결 n_external개 생성 (모두 외부 IP)."""
    conns = []
    for i in range(n_external):
        ip = f"8.8.8.{i % (unique_ips or n_external)}"
        port = 1000 + (i % (unique_ports or n_external))
        conns.append(
            FakeConn(
                laddr=FakeAddr("192.168.0.1", 50000 + i),
                raddr=FakeAddr(ip, port),
                pid=100 + i,
            )
        )
    return conns


def test_cap_truncates_at_10_and_raw_preserved():
    conns = _make_conns(15)
    with patch("agent_core.collector.network.psutil.net_io_counters", return_value=FakeNetIO()), \
         patch("agent_core.collector.network.psutil.net_connections", return_value=conns):
        nc = NetworkCollector()
        out = nc.collect()
    assert out["external_connection_count_raw"] == 15
    assert out["external_connection_count_truncated"] is True
    # cap=10 적용
    assert len(out["external_connections"]) == 10
    # 기존 키 보존 (raw count로 동작)
    assert out["external_connection_count"] == 15


def test_not_truncated_when_under_cap():
    conns = _make_conns(5)
    with patch("agent_core.collector.network.psutil.net_io_counters", return_value=FakeNetIO()), \
         patch("agent_core.collector.network.psutil.net_connections", return_value=conns):
        nc = NetworkCollector()
        out = nc.collect()
    assert out["external_connection_count_raw"] == 5
    assert out["external_connection_count_truncated"] is False
    assert len(out["external_connections"]) == 5


def test_unique_ip_port_process_counts():
    # 3개 동일 ip+port+pid (중복 2건), 2개 신규 ip
    conns = [
        FakeConn(FakeAddr("10.0.0.1", 50000), FakeAddr("8.8.8.8", 443), pid=1),
        FakeConn(FakeAddr("10.0.0.1", 50001), FakeAddr("8.8.8.8", 443), pid=1),
        FakeConn(FakeAddr("10.0.0.1", 50002), FakeAddr("8.8.8.8", 443), pid=1),
        FakeConn(FakeAddr("10.0.0.1", 50003), FakeAddr("9.9.9.9", 80), pid=2),
        FakeConn(FakeAddr("10.0.0.1", 50004), FakeAddr("1.1.1.1", 8080), pid=3),
    ]
    with patch("agent_core.collector.network.psutil.net_io_counters", return_value=FakeNetIO()), \
         patch("agent_core.collector.network.psutil.net_connections", return_value=conns):
        nc = NetworkCollector()
        out = nc.collect()
    assert out["unique_remote_ip_count"] == 3
    assert out["unique_remote_port_count"] == 3  # 443, 80, 8080
    assert out["unique_remote_process_count"] == 3
    assert out["duplicate_connection_count"] == 2  # (8.8.8.8,443,1) 동일 3건 → 중복 2
