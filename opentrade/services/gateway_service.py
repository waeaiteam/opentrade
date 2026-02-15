"""
OpenTrade 网关服务
"""

import asyncio
import json
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from opentrade.core.config import get_config
from opentrade.services.trade_executor import TradeExecutor


class GatewayService:
    """网关服务
    
    WebSocket 控制平面，
    负责接收指令、转发消息、管理会话。
    """

    def __init__(self):
        self.config = get_config()
        self.app = FastAPI(title="OpenTrade Gateway")
        self._connections: dict[str, WebSocket] = {}
        self._executor: TradeExecutor | None = None

        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""
        # CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # WebSocket 端点
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self._handle_websocket(websocket)

        # REST 端点
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

        @self.app.get("/api/v1/status")
        async def status():
            return {
                "status": "running",
                "mode": self._executor.mode if self._executor else "stopped",
                "connected": bool(self._executor and self._executor.exchange),
            }

        @self.app.get("/api/v1/positions")
        async def positions():
            if self._executor:
                return {"positions": list(self._executor.positions.values())}
            return {"positions": []}

        @self.app.post("/api/v1/trade/start")
        async def start_trading(mode: str = "paper"):
            if self._executor and self._executor.is_running:
                return {"status": "error", "message": "Already running"}

            self._executor = TradeExecutor(mode=mode)
            await self._executor.connect()

            # 启动交易循环
            asyncio.create_task(self._executor.start())

            return {"status": "ok", "mode": mode}

        @self.app.post("/api/v1/trade/stop")
        async def stop_trading():
            if self._executor:
                await self._executor.stop()
                self._executor = None

            return {"status": "ok"}

    async def _handle_websocket(self, websocket: WebSocket):
        """处理 WebSocket 连接"""
        await websocket.accept()

        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)

                # 处理消息
                response = await self._process_message(message)

                # 发送响应
                await websocket.send_text(json.dumps(response))

        except WebSocketDisconnect:
            pass

    async def _process_message(self, message: dict) -> dict:
        """处理消息"""
        command = message.get("command")
        params = message.get("params", {})

        if command == "ping":
            return {"status": "ok", "pong": True}

        elif command == "status":
            return {
                "status": "ok",
                "running": self._executor.is_running if self._executor else False,
                "positions": list(self._executor.positions.values()) if self._executor else [],
            }

        elif command == "start":
            mode = params.get("mode", "paper")
            self._executor = TradeExecutor(mode=mode)
            await self._executor.connect()
            await self._executor.start()
            return {"status": "ok", "mode": mode}

        elif command == "stop":
            if self._executor:
                await self._executor.stop()
                self._executor = None
            return {"status": "ok"}

        elif command == "positions":
            if self._executor:
                return {"status": "ok", "positions": list(self._executor.positions.values())}
            return {"status": "ok", "positions": []}

        elif command == "trade":
            # 手动下单
            if not self._executor:
                return {"status": "error", "message": "Executor not started"}

            # TODO: 实现手动下单
            return {"status": "ok", "message": "Trade executed"}

        else:
            return {"status": "error", "message": f"Unknown command: {command}"}

    async def run(self, host: str = "127.0.0.1", port: int = 18790):
        """运行网关"""
        import uvicorn

        self.config = get_config()

        print("[bold]🚀 启动 OpenTrade 网关...[/bold]")
        print(f"   REST API: http://{host}:{port}")
        print(f"   WebSocket: ws://{host}:{port}/ws")
        print()

        config = uvicorn.Config(self.app, host=host, port=port)
        server = uvicorn.Server(config)

        await server.serve()


def run_gateway(port: int = 18790, host: str = "127.0.0.1"):
    """运行网关 (同步入口)"""
    service = GatewayService()
    asyncio.run(service.run(host=host, port=port))
