"""Admin token auth — shared between admin_router 와 clear_router.

`RADA_ADMIN_TOKEN` 환경변수에 비어있지 않은 값이 설정되면 모든 admin/destructive
엔드포인트는 요청 헤더 `X-Admin-Token` 와 일치하는 토큰을 요구한다.

token 환경변수가 비어 있거나 미설정이면 (개발/테스트 기본값) 인증을 우회하여
기존 동작과 호환된다. 운영 배포에서는 반드시 토큰을 지정해야 한다.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException, status


def _expected_token() -> Optional[str]:
    raw = os.getenv("RADA_ADMIN_TOKEN", "")
    raw = raw.strip()
    return raw or None


def require_admin_token(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """FastAPI dependency. 토큰 불일치 시 401."""
    expected = _expected_token()
    if expected is None:
        # 미설정 → bypass (개발 기본).
        return
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Admin-Token",
        )


__all__ = ["require_admin_token"]
