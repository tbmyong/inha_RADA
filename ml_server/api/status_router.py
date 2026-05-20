"""GET /status — 서버 상태."""
from fastapi import APIRouter

from ..storage import pc_history_store, model_store
from ..detector.global_degradation import detect_global_hw_degradation
from ..silent_fail_counters import get_silent_fail_counters
from ..policy import get_scoring_policy, get_allowlist

router = APIRouter()


@router.get("/status")
def status():
    # 운영 중 reload 가능하므로 매 호출마다 최신 캐시 버전을 노출.
    try:
        sp_ver = get_scoring_policy().version
    except Exception:
        sp_ver = None
    try:
        al_ver = get_allowlist().version
    except Exception:
        al_ver = None
    return {
        "status":           "running",
        "monitored_pcs":    list(pc_history_store.pc_history.keys()),
        "total_pcs":        len(pc_history_store.all_pc_latest),
        "pc_history_sizes": {pc_id: len(h)
                             for pc_id, h in pc_history_store.pc_history.items()},
        "trained_models":   model_store.list_trained(),
        "global_hw_latest": detect_global_hw_degradation(),
        "silent_fail_counters": get_silent_fail_counters(),
        "scoring_policy_version": sp_ver,
        "allowlist_version":      al_ver,
    }
