"""재학습 트리거 — last_train_count 방식 (modulo 버그 회피)."""
from ..config import MIN_TRAIN_SIZE, RETRAIN_INTERVAL
from ..storage import pc_history_store, model_store
from ..detector.anomaly_predictor import train_model


def maybe_retrain(pc_id: str, slot: str) -> bool:
    """train_size - last_count >= RETRAIN_INTERVAL 이면 재학습."""
    train_size = len(pc_history_store.pc_train_history.get(pc_id, {}).get(slot, []))
    last_count = model_store.get_sample_count(pc_id, slot)

    if train_size >= MIN_TRAIN_SIZE and train_size - last_count >= RETRAIN_INTERVAL:
        if train_model(pc_id, slot):
            info = model_store.get_model(pc_id, slot)
            if info:
                print(f"[학습 완료] PC={pc_id}, 슬롯={slot}, 샘플={train_size}건, "
                      f"contamination={info['contamination']}, "
                      f"LOF윈도우={info['lof_window_size']}건, "
                      f"박스플롯필터={'O' if info['boxplot_filtered'] else 'X'}")
            return True
    return False
