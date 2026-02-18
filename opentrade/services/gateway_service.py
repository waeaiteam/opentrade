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


"""
OpenTrade 网关服务
"""

import asyncio
import json
from datetime import datetime
from typing import Callable, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from opentrade.core.config import get_config
from opentrade.services.trade_executor import TradeExecutor


class EventType:
    """事件类型"""
    TRADE = "trade"
    ORDER = "order"
    POSITION = "position"
    BALANCE = "balance"
    SIGNAL = "signal"
    ALERT = "alert"
    ERROR = "error"
    STATUS = "status"


class GatewayService:
    """网关服务

    WebSocket 控制平面，
    负责接收指令、转发消息、管理会话。
    支持事件推送和订阅。
    """

    def __init__(self):
        self.config = get_config()
        self.app = FastAPI(title="OpenTrade Gateway")
        self._connections: dict[str, WebSocket] = {}
        self._subscribers: dict[str, Set[WebSocket]] = {
            EventType.TRADE: set(),
            EventType.ORDER: set(),
            EventType.POSITION: set(),
            EventType.BALANCE: set(),
            EventType.SIGNAL: set(),
            EventType.ALERT: set(),
            EventType.ERROR: set(),
            EventType.STATUS: set(),
        }
        self._executor: TradeExecutor | None = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        
        self._setup_routes()
        self._start_event_broadcaster()

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

        @self.app.websocket("/ws/events")
        async def websocket_events(websocket: WebSocket):
            await self._handle_event_stream(websocket)

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

        @self.app.get("/api/v1/orders")
        async def orders():
            if self._executor:
                return {"orders": list(self._executor.orders.values())}
            return {"orders": []}

        @self.app.get("/api/v1/balance")
        async def balance():
            if self._executor:
                return {"balance": self._executor.balance}
            return {"balance": {}}

        @self.app.post("/api/v1/trade/start")
        async def start_trading(mode: str = "paper"):
            if self._executor and self._executor.is_running:
                return {"status": "error", "message": "Already running"}

            self._executor = TradeExecutor(mode=mode)
            await self._executor.connect()

            # 启动事件监听
            asyncio.create_task(self._listen_executor_events())

            # 启动交易循环
            asyncio.create_task(self._executor.start())

            return {"status": "ok", "mode": mode}

        @self.app.post("/api/v1/trade/stop")
        async def stop_trading():
            if self._executor:
                await self._executor.stop()
                self._executor = None

            return {"status": "ok"}

        @self.app.get("/api/v1/events")
        async def list_events():
            """列出可用的事件类型"""
            return {
                "events": list(self._subscribers.keys()),
                "subscriptions": {
                    event: len(subs) for event, subs in self._subscribers.items()
                }
            }

    async def _listen_executor_events(self):
        """监听执行器事件"""
        if not self._executor:
            return
        
        try:
            async for event in self._executor.event_stream():
                await self._event_queue.put(event)
        except asyncio.CancelledError:
            pass

    async def _start_event_broadcaster(self):
        """启动事件广播器"""
        while True:
            try:
                event = await self._event_queue.get()
                await self._broadcast_event(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[red]事件广播错误: {e}[/red]")

    async def _broadcast_event(self, event: dict):
        """广播事件到所有订阅者"""
        event_type = event.get("type", "unknown")
        subscribers = self._subscribers.get(event_type, set())
        
        # 广播到特定类型订阅者
        for ws in subscribers.copy():
            try:
                await ws.send_json(event)
            except Exception:
                subscribers.discard(ws)

        # 广播到所有订阅者
        all_subs = set()
        for subs in self._subscribers.values():
            all_subs.update(subs)
        
        for ws in all_subs.copy():
            if ws not in subscribers:
                try:
                    await ws.send_json(event)
                except Exception:
                    all_subs.discard(ws)

    async def _handle_event_stream(self, websocket: WebSocket):
        """处理事件流订阅"""
        await websocket.accept()
        
        # 订阅所有事件
        self._subscribers[EventType.TRADE].add(websocket)
        self._subscribers[EventType.ORDER].add(websocket)
        self._subscribers[EventType.POSITION].add(websocket)
        self._subscribers[EventType.SIGNAL].add(websocket)
        
        try:
            while True:
                # 保持连接活跃
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            # 取消订阅
            for subs in self._subscribers.values():
                subs.discard(websocket)

    async def emit_event(self, event_type: str, data: dict):
        """发射事件"""
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._event_queue.put(event)

    async def _handle_websocket(self, websocket: WebSocket):    async def _handle_websocket(self, websocket: WebSocket):
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
