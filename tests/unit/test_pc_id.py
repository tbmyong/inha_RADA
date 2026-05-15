"""agent_core.identity.pc_id 테스트."""
from agent_core.identity.pc_id import PC_ID, get_fixed_pc_id


def test_pc_id_is_nonempty_string():
    assert isinstance(PC_ID, str)
    assert len(PC_ID) > 0


def test_pc_id_is_stable_across_calls():
    a = get_fixed_pc_id()
    b = get_fixed_pc_id()
    assert a == b


def test_pc_id_length_bound():
    # MAC(12자) 또는 hostname(<=16자)
    assert len(PC_ID) <= 16


def test_pc_id_no_spaces():
    assert " " not in PC_ID
