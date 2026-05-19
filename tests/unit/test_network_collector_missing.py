"""F5 — NetworkCollector network_collection_missing_reason 키 검증.

수집 실패(권한/OS 오류)와 실제 빈 외부 연결을 구분한다.
"""
from __future__ import annotations

from unittest.mock import patch

from client_core.collector.network import NetworkCollector


def test_missing_reason_none_on_success():
    nc = NetworkCollector()
    out = nc.collect()
    assert "network_collection_missing_reason" in out
    # 정상 환경: None
    assert out["network_collection_missing_reason"] is None


def test_missing_reason_permission_error():
    nc = NetworkCollector()
    # 첫 호출은 워밍업 — _prev 채우기
    nc.collect()
    with patch(
        "client_core.collector.network.psutil.net_connections",
        side_effect=PermissionError("denied"),
    ):
        out = nc.collect()
    assert out["network_collection_missing_reason"] == "permission_error"
    # 외부 연결 카운트는 0 으로 보일 수 있지만, missing_reason 으로 구분 가능
    assert out["external_connection_count"] == 0


def test_missing_reason_os_error():
    nc = NetworkCollector()
    nc.collect()
    with patch(
        "client_core.collector.network.psutil.net_connections",
        side_effect=OSError("kernel oops"),
    ):
        out = nc.collect()
    assert out["network_collection_missing_reason"] == "os_error"


def test_missing_reason_unknown_for_other_exceptions():
    nc = NetworkCollector()
    nc.collect()
    with patch(
        "client_core.collector.network.psutil.net_connections",
        side_effect=RuntimeError("???"),
    ):
        out = nc.collect()
    assert out["network_collection_missing_reason"] == "unknown"


def test_real_empty_list_keeps_reason_none():
    nc = NetworkCollector()
    nc.collect()
    with patch(
        "client_core.collector.network.psutil.net_connections",
        return_value=[],
    ):
        out = nc.collect()
    # 실제 외부 연결 0개 — reason 은 None (수집은 성공)
    assert out["network_collection_missing_reason"] is None
    assert out["external_connection_count"] == 0
