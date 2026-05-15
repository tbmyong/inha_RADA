"""FastAPI app 엔트리포인트.

uvicorn ml_server.main:app --reload
또는 uvicorn ml_server:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.analyze_router import router as analyze_router
from .api.status_router import router as status_router
from .api.clear_router import router as clear_router
from .policy import load_scoring_policy, load_allowlist


@asynccontextmanager
async def lifespan(app: FastAPI):
    # fail-fast: 정책 로드 실패 시 startup 단계에서 즉시 RuntimeError 전파
    load_scoring_policy()
    load_allowlist()
    yield


app = FastAPI(
    title="PC 이상탐지 ML 서버 v8 (refactored)",
    lifespan=lifespan,
)

app.include_router(analyze_router)
app.include_router(status_router)
app.include_router(clear_router)
