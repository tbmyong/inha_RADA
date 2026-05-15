"""MetricsRequest.timestamp — ISO 8601 validator 단위 테스트."""
import pytest
from pydantic import ValidationError

from ml_server.model.requests import MetricsRequest


def _base(**overrides):
    base = dict(
        pc_id="pc-ts-1",
        timestamp="2026-05-13T10:00:00",
        cpu_percent=10.0,
        memory_percent=20.0,
        inbound_mb=0.0,
        outbound_mb=0.0,
        external_packet_count=0,
    )
    base.update(overrides)
    return base


def test_valid_iso_passes():
    m = MetricsRequest(**_base(timestamp="2026-05-13T12:34:56"))
    assert m.timestamp == "2026-05-13T12:34:56"


def test_not_a_date_raises():
    with pytest.raises(ValidationError):
        MetricsRequest(**_base(timestamp="not-a-date"))


def test_impossible_date_raises():
    with pytest.raises(ValidationError):
        MetricsRequest(**_base(timestamp="2026-13-99"))
