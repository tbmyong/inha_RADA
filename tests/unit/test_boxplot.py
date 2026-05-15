"""agent_core.detector.boxplot 테스트."""
from agent_core.detector import BoxplotDetector
from agent_core.window import SlidingWindow


def _push(window, cpu_seq, mem_seq):
    for c, m in zip(cpu_seq, mem_seq):
        window.append({"cpu_percent": c, "memory_percent": m})


def test_unavailable_when_too_few_samples():
    det = BoxplotDetector(min_window=12)
    w = SlidingWindow(36)
    _push(w, [10, 20, 30], [10, 20, 30])
    out = det.compute(w)
    assert out["available"] is False


def test_outlier_flag_when_current_spikes():
    det = BoxplotDetector(min_window=12)
    w = SlidingWindow(36)
    # IQR이 양수가 되도록 약간의 변동을 주고, 마지막을 명확한 이상치로
    base = [18, 20, 22, 19, 21, 20, 22, 19, 21, 20, 22, 18, 21, 20, 99]
    _push(w, base, base)
    out = det.compute(w)
    assert out["available"] is True
    assert out["cpu_iqr_outlier"] is True
    assert out["mem_iqr_outlier"] is True
    assert out["cpu_deviation"] > 0


def test_normal_when_current_in_range():
    det = BoxplotDetector(min_window=12)
    w = SlidingWindow(36)
    base = [20, 22, 19, 21, 23, 20, 22, 21, 19, 20, 22, 21, 20, 22, 21]
    _push(w, base, base)
    out = det.compute(w)
    assert out["available"] is True
    assert out["cpu_iqr_outlier"] is False


def test_quartiles_are_python_floats():
    det = BoxplotDetector(min_window=12)
    w = SlidingWindow(36)
    base = list(range(15))
    _push(w, base, base)
    out = det.compute(w)
    # JSON 직렬화 가능한 기본 타입
    import json
    json.dumps(out)
    assert isinstance(out["cpu_q1"], float)
    assert isinstance(out["cpu_q3"], float)


def test_window_size_reported():
    det = BoxplotDetector(min_window=12)
    w = SlidingWindow(36)
    base = [50] * 13
    _push(w, base, base)
    out = det.compute(w)
    assert out["window_size"] == 13
