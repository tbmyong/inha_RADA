"""F5 — signal_extractor 가 수집 실패를 인식하고 신호를 drop / signals_missing 채우는지 검증."""
from collections import deque

from ml_server.scorer.signal_extractor import extract_signals
from ml_server.model.requests import MetricsRequest


def _metrics(**overrides):
    base = dict(
        pc_id="pc-1", timestamp="2026-05-19T10:00:00",
        cpu_percent=10.0, memory_percent=20.0,
        inbound_mb=0.0, outbound_mb=0.0, external_packet_count=0,
    )
    base.update(overrides)
    return MetricsRequest(**base)


def test_signals_missing_empty_on_clean_payload():
    m = _metrics()
    pack = extract_signals(m, deque(), slot="free")
    assert pack.get("signals_missing") == []


def test_network_missing_marks_signals_missing_and_drops_network_signals():
    # 네트워크 수집 실패: external_packet_count=10 처럼 0이 아닌 값이라도
    # missing_reason 이 있으면 net_external_high 등은 False 로 drop.
    m = _metrics(
        external_packet_count=20,
        external_connections=[{"ip": "155.138.99.1"}],  # mining pool 매치
        derived_features={
            "network_collection_missing_reason": "permission_error",
        },
    )
    pack = extract_signals(m, deque(), slot="free")
    assert "network" in pack["signals_missing"]
    signals = pack["signals"]
    # network-카테고리 신호는 점수에 반영되지 않도록 False
    assert signals["net_external_high"] is False
    assert signals["mining_pool_ip"] is False


def test_process_missing_marks_signals_missing_and_drops_process_signals():
    m = _metrics(
        top_processes=[
            {"name": "xmrig.exe", "cpu_percent": 90, "memory_percent": 5, "path": "C:\\x"}
        ],
        derived_features={
            "process_collection_missing_reason": "permission_error",
        },
    )
    pack = extract_signals(m, deque(), slot="free")
    assert "process" in pack["signals_missing"]
    # xmrig가 top_processes 에 있어도 process 수집 실패면 known_miner=False
    assert pack["signals"]["known_miner"] is False


def test_both_missing_listed():
    m = _metrics(derived_features={
        "network_collection_missing_reason": "os_error",
        "process_collection_missing_reason": "unknown",
        "derived_missing_reasons": {"network_derived": "ValueError"},
    })
    pack = extract_signals(m, deque(), slot="free")
    sm = pack["signals_missing"]
    assert "network" in sm
    assert "process" in sm
    assert "derived_features" in sm
