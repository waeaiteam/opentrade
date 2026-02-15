"""
OpenTrade Web API - FastAPI

提供 REST API 和 WebSocket 接口
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from rich import print

from opentrade.core.config import get_config


# ============ WebSocket 连接管理 ============

class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


# ============ Pydantic Models ============

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "healthy"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    version: str = "1.0.0-alpha"
    database: str = "connected"
    redis: str = "connected"


class OrderRequest(BaseModel):
    """订单请求"""
    symbol: str = Field(..., example="BTC/USDT")
    side: str = Field(..., example="buy")
    order_type: str = Field(..., example="market")
    size: float = Field(..., gt=0, example=0.1)
    price: Optional[float] = Field(None, example=50000)
    leverage: float = Field(default=1.0, ge=1, le=100)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class OrderResponse(BaseModel):
    """订单响应"""
    id: str
    symbol: str
    side: str
    status: str
    size: float
    filled_size: float = 0.0
    average_price: Optional[float] = None
    created_at: str


class PositionResponse(BaseModel):
    """持仓响应"""
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    pnl: float
    pnl_pct: float


class BalanceResponse(BaseModel):
    """余额响应"""
    total_equity: float
    available: float
    positions_value: float


# ============ FastAPI App ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    print("[API] 🚀 Web 服务启动")
    yield
    print("[API] 👋 Web 服务停止")


app = FastAPI(
    title="OpenTrade API",
    description="开源 AI 交易系统 API",
    version="1.0.0-alpha",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件 (简单状态页)
app.mount("/static", StaticFiles(directory="opentrade/web/static"), name="static")


# ============ REST Endpoints ============

@app.get("/", response_model=dict)
async def root():
    """API 根路径"""
    return {
        "name": "OpenTrade API",
        "version": "1.0.0-alpha",
        "docs": "/docs",
        "status": "/health",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/api/v1/status")
async def get_status():
    """获取系统状态"""
    from opentrade.core.database import check_connection

    db_status = "connected" if check_connection() else "disconnected"

    return {
        "status": "running",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/v1/orders", response_model=OrderResponse)
async def create_order(order: OrderRequest):
    """创建订单"""
    from opentrade.core.gateway import OrderGateway, create_market_order
    from opentrade.core.config import get_config

    config = get_config()

    # 创建订单请求
    order_req = create_market_order(
        symbol=order.symbol,
        side=order.side,
        size=order.size,
        leverage=order.leverage,
        source="api",
    )

    # 通过网关提交
    gateway = OrderGateway(None, config)  # 无交易所 (模拟)
    try:
        result = await gateway.submit(order_req)
        return {
            "id": result.id,
            "symbol": result.symbol,
            "side": result.side.value,
            "status": result.status.value,
            "size": result.size,
            "filled_size": result.filled_size,
            "average_price": result.average_price,
            "created_at": result.created_at.isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/orders")
async def get_orders(symbol: Optional[str] = None):
    """获取订单列表"""
    from opentrade.core.gateway import OrderGateway

    gateway = OrderGateway(None)
    orders = gateway.get_orders(symbol=symbol)
    return {"orders": [o.model_dump() for o in orders]}


@app.get("/api/v1/positions")
async def get_positions():
    """获取当前持仓"""
    return {"positions": []}


@app.get("/api/v1/balance", response_model=BalanceResponse)
async def get_balance():
    """获取账户余额"""
    return BalanceResponse(
        total_equity=0.0,
        available=0.0,
        positions_value=0.0,
    )


@app.get("/api/v1/strategies")
async def get_strategies():
    """获取策略列表"""
    return {"strategies": []}


@app.post("/api/v1/strategies/{strategy_id}/enable")
async def enable_strategy(strategy_id: str):
    """启用策略"""
    return {"status": "enabled", "strategy_id": strategy_id}


@app.post("/api/v1/strategies/{strategy_id}/disable")
async def disable_strategy(strategy_id: str):
    """禁用策略"""
    return {"status": "disabled", "strategy_id": strategy_id}


# ============ WebSocket Endpoints ============

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时数据"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # 处理消息
            await websocket.send_json({"echo": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    """订单状态 WebSocket"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "order_update", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============ 错误处理 ============

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    return {"detail": str(exc)}


if __name__ == "__main__":
    import uvicorn

    config = get_config()

    uvicorn.run(
        "opentrade.web.api:app",
        host=config.gateway.host,
        port=config.gateway.web_port,
        reload=True,
    )
