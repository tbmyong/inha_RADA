"""학습된 모델 저장소 (threading.Lock atomic swap)."""
import threading
from typing import Dict, Optional

# pc_id → {slot → model_dict}
pc_models: Dict[str, Dict[str, dict]] = {}

_lock = threading.Lock()


def get_model(pc_id: str, slot: str) -> Optional[dict]:
    with _lock:
        return pc_models.get(pc_id, {}).get(slot)


def set_model(pc_id: str, slot: str, new_model: dict) -> None:
    """원자적 swap — 예측 중인 스레드가 절반만 갱신된 모델을 보지 않도록 보호."""
    with _lock:
        if pc_id not in pc_models:
            pc_models[pc_id] = {}
        pc_models[pc_id][slot] = new_model


def get_sample_count(pc_id: str, slot: str) -> int:
    with _lock:
        return pc_models.get(pc_id, {}).get(slot, {}).get("sample_count", 0)


def list_trained() -> Dict[str, list]:
    with _lock:
        return {pc_id: list(slots.keys()) for pc_id, slots in pc_models.items()}


def clear_pc(pc_id: str) -> bool:
    """주어진 pc_id의 모든 슬롯 모델 정리 (lock 보호). 흔적 존재 시 True."""
    with _lock:
        return pc_models.pop(pc_id, None) is not None
