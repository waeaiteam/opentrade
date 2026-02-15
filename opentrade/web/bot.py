"""
OpenTrade Web Interface - Web + Bot + SDK

包含:
1. Web Dashboard (静态 HTML)
2. Telegram Bot
3. Python SDK
"""

# ============ Telegram Bot ============

class TelegramBot:
    """Telegram 交易机器人"""

    def __init__(self, token: str, executor, coordinator):
        self.token = token
        self.executor = executor
        self.coordinator = coordinator
        self._running = False

    async def start(self):
        """启动机器人"""
        print("[Telegram] Bot started")

    async def handle_command(self, command: str, args: list, user_id: str) -> str:
        """处理命令"""
        commands = {
            "status": self._cmd_status,
            "balance": self._cmd_balance,
            "positions": self._cmd_positions,
            "buy": self._cmd_buy,
            "sell": self._cmd_sell,
            "close": self._cmd_close,
            "analyze": self._cmd_analyze,
            "help": self._cmd_help,
        }

        handler = commands.get(command)
        if handler:
            return await handler(args, user_id)
        return f"未知命令: {command}"

    async def _cmd_status(self, args: list, user_id: str) -> str:
        """状态命令"""
        return "系统运行中\n交易所: 已连接\n策略: Paper"

    async def _cmd_balance(self, args: list, user_id: str) -> str:
        """余额命令"""
        balance = await self.executor.get_balance()
        return f"总资产: {balance.total_balance:.2f}\n可用: {balance.available_balance:.2f}"

    async def _cmd_positions(self, args: list, user_id: str) -> str:
        """持仓命令"""
        positions = await self.executor.get_positions()
        if not positions:
            return "无持仓"
        lines = [f"{p.symbol}: {p.quantity} @ {p.entry_price:.2f} PnL: {p.pnl_pct:.1%}" for p in positions]
        return "\n".join(lines)

    async def _cmd_buy(self, args: list, user_id: str) -> str:
        """买入命令"""
        if len(args) < 2:
            return "用法: /buy <symbol> <quantity>"
        symbol, quantity = args[0], float(args[1])
        order = await self.executor.buy(symbol, quantity)
        return f"买入订单: {order.order_id}\n状态: {order.status.value}"

    async def _cmd_sell(self, args: list, user_id: str) -> str:
        """卖出命令"""
        if len(args) < 2:
            return "用法: /sell <symbol> <quantity>"
        symbol, quantity = args[0], float(args[1])
        order = await self.executor.sell(symbol, quantity)
        return f"卖出订单: {order.order_id}\n状态: {order.status.value}"

    async def _cmd_close(self, args: list, user_id: str) -> str:
        """平仓命令"""
        if len(args) < 1:
            return "用法: /close <symbol>"
        symbol = args[0]
        order = await self.executor.close_position(symbol, "LONG")
        return f"平仓订单: {order.order_id}\n状态: {order.status.value}"

    async def _cmd_analyze(self, args: list, user_id: str) -> str:
        """分析命令"""
        if len(args) < 1:
            return "用法: /analyze <symbol>"
        symbol = args[0]
        ticker = await self.executor.get_ticker(symbol)
        if not ticker:
            return f"获取 {symbol} 失败"
        decision = await self.coordinator.analyze(symbol, ticker.price, {})
        return f"分析: {decision.summary}\n操作: {decision.action}\n置信度: {decision.confidence:.0%}"

    async def _cmd_help(self, args: list, user_id: str) -> str:
        """帮助命令"""
        return """
可用命令:
/status - 系统状态
/balance - 账户余额
/positions - 当前持仓
/buy <symbol> <quantity> - 买入
/sell <symbol> <quantity> - 卖出
/close <symbol> - 平仓
/analyze <symbol> - AI 分析
        """


# ============ Python SDK ============

class OpenTradeSDK:
    """
    OpenTrade Python SDK

    简单易用的 Python 接口
    """

    def __init__(
        self,
        exchange: str = "simulated",
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
    ):
        from opentrade.engine import create_simulated_executor, create_ccxt_executor

        if exchange == "simulated":
            self.executor = create_simulated_executor()
        else:
            self.executor = create_ccxt_executor(exchange, api_key, api_secret, testnet=testnet)

    @property
    def balance(self):
        """账户余额"""
        import asyncio
        return asyncio.run(self.executor.get_balance())

    def buy(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ):
        """买入"""
        import asyncio
        return asyncio.run(self.executor.buy(
            symbol, quantity, price, stop_loss=stop_loss, take_profit=take_profit
        ))

    def sell(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ):
        """卖出"""
        import asyncio
        return asyncio.run(self.executor.sell(
            symbol, quantity, price, stop_loss=stop_loss, take_profit=take_profit
        ))

    @property
    def positions(self):
        """持仓"""
        import asyncio
        return asyncio.run(self.executor.get_positions())

    def close(self, symbol: str, side: str = "LONG"):
        """平仓"""
        import asyncio
        from opentrade.engine import PositionSide
        pside = PositionSide(side)
        return asyncio.run(self.executor.close_position(symbol, pside))

    def ticker(self, symbol: str):
        """行情"""
        import asyncio
        return asyncio.run(self.executor.get_ticker(symbol))

    def analyze(self, symbol: str, **kwargs):
        """AI 分析"""
        from opentrade.agents.coordinator import AgentCoordinator
        import asyncio

        coordinator = AgentCoordinator()
        ticker = self.ticker(symbol)
        return asyncio.run(coordinator.analyze(
            symbol, ticker.price, kwargs if kwargs else {}
        ))


# ============ 便捷函数 ============

def connect(
    exchange: str = "simulated",
    api_key: str = "",
    api_secret: str = "",
    testnet: bool = True,
) -> OpenTradeSDK:
    """创建 SDK 连接"""
    return OpenTradeSDK(exchange, api_key, api_secret, testnet)


# ============ 导出 ============

__all__ = [
    "TelegramBot",
    "OpenTradeSDK",
    "connect",
]
