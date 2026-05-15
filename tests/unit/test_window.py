"""client_core.window.SlidingWindow 테스트."""
import pytest

from client_core.window import SlidingWindow


def test_basic_append_and_len():
    w = SlidingWindow(3)
    assert len(w) == 0
    w.append({"x": 1})
    w.append({"x": 2})
    assert len(w) == 2


def test_overflow_drops_oldest():
    w = SlidingWindow(3)
    for i in range(5):
        w.append({"x": i})
    items = w.to_list()
    assert len(items) == 3
    assert [it["x"] for it in items] == [2, 3, 4]


def test_is_full():
    w = SlidingWindow(2)
    assert not w.is_full()
    w.append(1)
    assert not w.is_full()
    w.append(2)
    assert w.is_full()


def test_clear():
    w = SlidingWindow(3)
    w.extend([1, 2, 3])
    assert len(w) == 3
    w.clear()
    assert len(w) == 0


def test_invalid_size_raises():
    with pytest.raises(ValueError):
        SlidingWindow(0)
    with pytest.raises(ValueError):
        SlidingWindow(-1)


def test_iteration_in_order():
    w = SlidingWindow(4)
    w.extend([10, 20, 30])
    assert list(w) == [10, 20, 30]
