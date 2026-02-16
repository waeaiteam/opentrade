"""
OpenTrade Backend - FastAPI Server

README 要求: uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

这里创建 backend/main.py 作为入口
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentrade.web.api import app as api_app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info("🚀 OpenTrade Backend starting...")
    yield
    logger.info("🛑 OpenTrade Backend stopped")


# 使用 api.py 中定义的 app
app = api_app


# CORS (确保在 app 上添加)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "name": "OpenTrade",
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
