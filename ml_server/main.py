"""FastAPI app 엔트리포인트.

uvicorn ml_server.main:app --reload
또는 uvicorn ml_server:app --reload
"""
from fastapi import FastAPI

from .api.analyze_router import router as analyze_router
from .api.status_router import router as status_router
from .api.clear_router import router as clear_router

app = FastAPI(title="PC 이상탐지 ML 서버 v8 (refactored)")

app.include_router(analyze_router)
app.include_router(status_router)
app.include_router(clear_router)
