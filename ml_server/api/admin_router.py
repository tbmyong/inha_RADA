"""Admin endpoints — 정책 YAML runtime reload 등.

운영 중 scoring_policy.yaml / allowlist.yaml 을 튜닝해도 컨테이너 재시작 없이
캐시를 갱신할 수 있도록 한다. fail-fast: 검증 실패 시 500 + 기존 캐시 유지가
아니라 캐시는 비워진 채로 예외를 전파한다 (loader.reload_policies 동작).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from ..policy import reload_policies, get_scoring_policy, get_allowlist
from .admin_auth import require_admin_token

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reload-policy", dependencies=[Depends(require_admin_token)])
def reload_policy() -> Dict[str, Any]:
    try:
        reload_policies()
    except Exception as e:
        log.exception("policy reload failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"policy reload failed: {type(e).__name__}: {e}",
        )
    sp = get_scoring_policy()
    al = get_allowlist()
    log.info(
        "policy reloaded scoring_version=%s allowlist_version=%s",
        sp.version,
        al.version,
    )
    return {
        "status": "ok",
        "scoring_policy_version": sp.version,
        "allowlist_version": al.version,
    }
