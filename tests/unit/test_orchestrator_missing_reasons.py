"""F5 — Orchestrator derived_features 가 collector 미수신 사유를 surface 하는지 검증."""
from __future__ import annotations

from unittest.mock import patch

from client_core.collector.orchestrator import CollectorOrchestrator
from client_core.collector.process import ProcessCollector


def test_derived_features_carries_collector_reasons_on_success():
    orch = CollectorOrchestrator(pc_id="pc-test")
    m = orch.collect()
    df = m.get("derived_features")
    assert df is not None
    assert "network_collection_missing_reason" in df
    assert "process_collection_missing_reason" in df
    assert "gpu_metrics_missing_reason" in df
    # 정상 시 network/process 는 None
    assert df["network_collection_missing_reason"] is None
    assert df["process_collection_missing_reason"] is None


def test_derived_features_surfaces_process_missing_reason():
    pc = ProcessCollector()
    orch = CollectorOrchestrator(pc_id="pc-test", process=pc)
    with patch(
        "client_core.collector.process.psutil.process_iter",
        side_effect=PermissionError("denied"),
    ):
        m = orch.collect()
    df = m["derived_features"]
    assert df["process_collection_missing_reason"] == "permission_error"
    # 22키 페이로드는 보존 — top_processes 는 빈 리스트지만 키 자체는 존재
    assert "top_processes" in m
    assert m["top_processes"] == []


def test_derived_features_surfaces_network_missing_reason():
    orch = CollectorOrchestrator(pc_id="pc-test")
    # 첫 collect 로 워밍업
    orch.collect()
    with patch(
        "client_core.collector.network.psutil.net_connections",
        side_effect=PermissionError("denied"),
    ):
        m = orch.collect()
    df = m["derived_features"]
    assert df["network_collection_missing_reason"] == "permission_error"
