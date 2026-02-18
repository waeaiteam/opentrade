"""
OpenTrade 交易执行器
"""

import asyncio
from datetime import datetime
from uuid import uuid4

from opentrade.agents.base import SignalType, TradeDecision
from opentrade.core.config import get_config
from opentrade.core.database import db
from opentrade.models.position import Position
from opentrade.models.trade import CloseReason, Trade, TradeAction, TradeSide, TradeStatus


class TradeExecutor:
    """交易执行器

    负责执行交易决策、管理仓位、
    风险控制和平仓逻辑。
    """

    def __init__(self, mode: str = "paper"):
        """初始化

        Args:
            mode: paper(模拟) / live(实盘)
        """
        self.mode = mode
        self.config = get_config()
        self.exchange = None  # 交易所连接
        self.positions: dict[str, Position] = {}
        self.active = False
        self._running = False

    async def connect(self):
        """连接交易所"""
        from opentrade.plugins.exchanges import get_exchange

        exchange_config = self.config.exchange
        self.exchange = get_exchange(
            exchange_config.name,
            api_key=exchange_config.api_key,
            api_secret=exchange_config.api_secret,
            testnet=exchange_config.testnet,
        )

        if self.mode == "live":
            await self.exchange.connect()
        else:
            await self.exchange.connect(testnet=True)

        # 同步持仓
        await self._sync_positions()

    async def _sync_positions(self):
        """同步持仓"""
        positions = await self.exchange.fetch_positions()
        for p in positions:
            symbol = p["symbol"]
            self.positions[symbol] = p

    async def start(
        self,
        symbols: list[str] = None,
        leverage: float = 1.0,
        interval: int = 60,
    ):
        """启动交易循环

        Args:
            symbols: 交易标的列表
            leverage: 杠杆倍数
            interval: 检查间隔(秒)
        """
        if self._running:
            return

        self._running = True
        self.active = True

        symbols = symbols or ["BTC/USDT", "ETH/USDT"]

        print(f"[bold]🚀 启动交易执行器 ({self.mode}模式)[/bold]")
        print(f"   标的: {symbols}")
        print(f"   杠杆: {leverage}x")
        print()

        while self._running:
            try:
                # 获取市场数据
                for symbol in symbols:
                    await self._process_symbol(symbol, leverage)

                # 等待
                await asyncio.sleep(interval)

            except Exception as e:
                print(f"[red]交易循环错误: {e}[/red]")
                await asyncio.sleep(5)

    async def _process_symbol(self, symbol: str, leverage: float):
        """处理单个标的"""
        # 获取当前决策
        decision = await self._get_decision(symbol)
        if not decision:
            return

        # 风控检查
        risk_check = self._check_risk(decision)
        decision.risk_check_passed = risk_check["passed"]
        decision.validation_errors = risk_check.get("errors", [])

        if not risk_check["passed"]:
            print(f"[yellow]⏭️  风控拦截: {symbol} {decision.action.value}[/yellow]")
            return

        # 执行交易
        await self._execute_decision(decision, leverage)

    async def _get_decision(self, symbol: str) -> TradeDecision | None:
        """获取交易决策"""
        from opentrade.agents.coordinator import CoordinatorAgent
        from opentrade.services.data_service import data_service

        # 获取市场状态
        market_state = await data_service.get_market_state(symbol)
        if not market_state:
            return None

        # 获取当前持仓
        position = self.positions.get(symbol)

        # 协调 Agent 分析
        agent = CoordinatorAgent()
        decision = await agent.analyze(
            market_state=market_state,
            positions=[position] if position else [],
        )

        return decision

    def _check_risk(self, decision: TradeDecision) -> dict:
        """风控检查"""
        errors = []

        # 检查置信度
        if decision.confidence.overall < 0.4:
            errors.append(f"置信度过低: {decision.confidence.overall:.2%}")

        # 检查风险评分
        if decision.risk_score > 0.7:
            errors.append(f"风险过高: {decision.risk_score:.2f}")

        # 检查仓位
        if decision.size > self.config.risk.max_position_pct:
            errors.append(f"仓位过大: {decision.size:.2%}")

        # 检查杠杆
        if decision.leverage > self.config.risk.max_leverage:
            errors.append(f"杠杆过大: {decision.leverage}x")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
        }

    async def _execute_decision(self, decision: TradeDecision, leverage: float):
        """执行决策"""
        symbol = decision.symbol

        # 获取当前持仓
        position = self.positions.get(symbol)
        has_position = position and position["size"] > 0

        if decision.action == SignalType.HOLD:
            # 持仓更新
            if has_position:
                await self._update_sl_tp(position, decision)
            return

        if decision.action in [SignalType.BUY, SignalType.SHORT]:
            # 开仓
            if has_position:
                # 检查是否同方向
                is_long = decision.action == SignalType.BUY
                if (is_long and position["side"] == "long") or (not is_long and position["side"] == "short"):
                    # 加仓
                    await self._add_position(position, decision)
                else:
                    # 反向，先平仓再开
                    await self._close_position(position, reason=CloseReason.REVERSAL)
                    await self._open_position(decision, leverage)
            else:
                await self._open_position(decision, leverage)

        elif decision.action in [SignalType.SELL, SignalType.COVER]:
            # 平仓
            if has_position:
                await self._close_position(
                    position,
                    reason=CloseReason.MANUAL if decision.action == SignalType.SELL else CloseReason.TAKE_PROFIT
                )

        # 更新持仓
        await self._sync_positions()

    async def _open_position(self, decision: TradeDecision, leverage: float):
        """开仓"""
        side = "long" if decision.action == SignalType.BUY else "short"

        # 计算数量
        balance = await self.exchange.fetch_balance()
        available = balance["available"]
        position_size = available * decision.size * leverage

        # 下单
        _order = await self.exchange.create_order(
            symbol=decision.symbol,
            side=side,
            type="market",
            amount=position_size,
            leverage=leverage,
        )

        # 保存交易记录
        trade = Trade(
            id=uuid4(),
            symbol=decision.symbol,
            exchange=self.config.exchange.name,
            side=TradeSide.LONG if side == "long" else TradeSide.SHORT,
            action=TradeAction.OPEN,
            status=TradeStatus.PENDING,
            quantity=position_size,
            leverage=leverage,
            entry_time=datetime.utcnow(),
            strategy_id=decision.strategy_id,
        )

        async with db.session() as session:
            session.add(trade)

        print(f"[green]✅ 开仓: {decision.symbol} {side} {position_size}[/green]")

    async def _close_position(self, position: dict, reason: CloseReason):
        """平仓"""
        symbol = position["symbol"]
        side = "long" if position["side"] == "long" else "short"

        # 市价平仓
        _order = await self.exchange.close_position(symbol, side)

        print(f"[yellow]🔴 平仓: {symbol} ({reason.value})[/yellow]")

    async def _add_position(self, position: dict, decision: TradeDecision):
        """加仓"""
        # TODO: 实现加仓逻辑
        pass

    async def _update_sl_tp(self, position: dict, decision: TradeDecision):
        """更新止盈止损"""
        if decision.stop_loss_pct:
            await self.exchange.set_stop_loss(
                position["symbol"],
                position["side"],
                decision.stop_loss_pct,
            )
        if decision.take_profit_pct:
            await self.exchange.set_take_profit(
                position["symbol"],
                position["side"],
                decision.take_profit_pct,
            )

    async def stop(self):
        """停止交易"""
        self._running = False
        print("[yellow]🛑 交易执行器已停止[/yellow]")

    @property
    def is_running(self) -> bool:
        return self._running
    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def balance(self) -> dict:
        """获取余额"""
        return getattr(self, '_balance', {})

    async def event_stream(self):
        """事件流

        生成器，产出交易事件
        """
        while True:
            try:
                # 等待新事件
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break

    async def _emit_status_event(self, status: str, message: str = ""):
        """发射状态事件"""
        event = {
            "type": "status",
            "data": {
                "status": status,
                "message": message,
                "mode": self.mode,
                "positions_count": len(self.positions),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        return event

    async def _emit_trade_event(self, trade):
        """发射交易事件"""
        event = {
            "type": "trade",
            "data": {
                "id": str(trade.id) if hasattr(trade, 'id') else str(uuid4()),
                "symbol": trade.symbol if hasattr(trade, 'symbol') else "",
                "side": str(trade.side) if hasattr(trade, 'side') else "",
                "action": str(trade.action) if hasattr(trade, 'action') else "",
                "price": trade.entry_price if hasattr(trade, 'entry_price') else 0,
                "size": trade.size if hasattr(trade, 'size') else 0,
                "pnl": trade.pnl if hasattr(trade, 'pnl') else 0,
                "status": str(trade.status) if hasattr(trade, 'status') else "",
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        return event

if __name__ == "__main__":
    # 测试
    pass
