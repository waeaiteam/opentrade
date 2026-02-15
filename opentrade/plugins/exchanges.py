"""
OpenTrade 交易所插件
"""

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime

import ccxt.async_support as ccxt

from opentrade.plugins.base import BasePlugin


@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str
    side: str  # long / short
    size: float
    entry_price: float
    mark_price: float = 0
    liquidation_price: float = 0
    pnl: float = 0
    pnl_percent: float = 0


@dataclass
class OrderInfo:
    """订单信息"""
    id: str
    symbol: str
    side: str
    type: str
    status: str
    amount: float
    filled: float
    price: float
    created_at: datetime


class ExchangePlugin(BasePlugin):
    """交易所插件基类"""

    def __init__(self, name: str, config: dict = None):
        super().__init__(config)
        self.name = name
        self._exchange: ccxt.Exchange | None = None

    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """交易所 ID (CCXT)"""
        pass

    async def initialize(self):
        """初始化连接"""
        if self._exchange:
            return

        self._exchange = self._create_exchange()
        await self._exchange.load_markets()

    @abstractmethod
    def _create_exchange(self) -> ccxt.Exchange:
        """创建 CCXT 交易所实例"""
        pass

    async def fetch_balance(self) -> dict:
        """获取余额"""
        if not self._exchange:
            await self.initialize()

        balance = await self._exchange.fetch_balance()
        return {
            "total": balance["total"],
            "free": balance["free"],
            "used": balance["used"],
        }

    async def fetch_positions(self) -> list[PositionInfo]:
        """获取持仓"""
        if not self._exchange:
            await self.initialize()

        positions = await self._exchange.fetch_positions()

        result = []
        for p in positions:
            result.append(PositionInfo(
                symbol=p["symbol"],
                side=p["side"],
                size=p["contracts"] or p["amount"] or 0,
                entry_price=p.get("entryPrice", 0),
                mark_price=p.get("markPrice", 0),
                liquidation_price=p.get("liquidationPrice", 0),
                pnl=p.get("unrealizedPnl", 0),
            ))

        return result

    async def create_order(
        self,
        symbol: str,
        side: str,
        type: str,
        amount: float,
        price: float = None,
        leverage: float = 1.0,
        stop_loss: float = None,
        take_profit: float = None,
    ) -> OrderInfo:
        """创建订单"""
        if not self._exchange:
            await self.initialize()

        params = {}
        if leverage > 1:
            params["leverage"] = leverage

        order_params = {}
        if stop_loss:
            order_params["stopLossPrice"] = stop_loss
        if take_profit:
            order_params["takeProfitPrice"] = take_profit

        if type == "market":
            if stop_loss or take_profit:
                order = await self._exchange.create_order(
                    symbol, side, "market", amount, params=order_params
                )
            else:
                order = await self._exchange.create_order(
                    symbol, side, "market", amount
                )
        else:
            order = await self._exchange.create_order(
                symbol, side, "limit", amount, price, params=params
            )

        return OrderInfo(
            id=order["id"],
            symbol=order["symbol"],
            side=order["side"],
            type=order["type"],
            status=order["status"],
            amount=order["amount"],
            filled=order.get("filled", 0),
            price=order.get("price", 0),
            created_at=datetime.fromtimestamp(order["timestamp"] / 1000),
        )

    async def close_position(self, symbol: str, side: str) -> OrderInfo:
        """平仓"""
        if not self._exchange:
            await self.initialize()

        # 市价平仓
        opposite = "sell" if side == "long" else "buy"
        order = await self._exchange.create_order(
            symbol, opposite, "market", None
        )

        return OrderInfo(
            id=order["id"],
            symbol=symbol,
            side=opposite,
            type="market",
            status=order["status"],
            amount=order.get("amount", 0),
            filled=order.get("filled", 0),
            price=order.get("price", 0),
            created_at=datetime.fromtimestamp(order["timestamp"] / 1000),
        )

    async def set_leverage(self, symbol: str, leverage: float):
        """设置杠杆"""
        if not self._exchange:
            await self.initialize()

        await self._exchange.set_leverage(symbol, leverage)

    async def set_stop_loss(self, symbol: str, side: str, stop_loss_pct: float):
        """设置止损"""
        # TODO: 实现
        pass

    async def set_take_profit(self, symbol: str, side: str, take_profit_pct: float):
        """设置止盈"""
        # TODO: 实现
        pass

    async def cancel_all_orders(self, symbol: str):
        """取消所有订单"""
        if not self._exchange:
            await self.initialize()

        await self._exchange.cancel_all_orders(symbol)

    async def shutdown(self):
        """关闭连接"""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None


# 交易所工厂
_exchange_plugins: dict[str, type[ExchangePlugin]] = {}


def register_exchange(name: str):
    """注册交易所"""
    def decorator(cls):
        _exchange_plugins[name] = cls
        return cls
    return decorator


def get_exchange(
    name: str,
    api_key: str = None,
    api_secret: str = None,
    testnet: bool = False,
) -> ExchangePlugin:
    """获取交易所实例"""
    if name not in _exchange_plugins:
        # 尝试使用 CCXT 原生
        return CCXTExchangePlugin(name, api_key, api_secret, testnet)

    plugin_class = _exchange_plugins[name]
    return plugin_class({
        "api_key": api_key,
        "api_secret": api_secret,
        "testnet": testnet,
    })


class CCXTExchangePlugin(ExchangePlugin):
    """CCXT 通用交易所插件"""

    def __init__(
        self,
        name: str,
        api_key: str = None,
        api_secret: str = None,
        testnet: bool = False,
    ):
        super().__init__(name, {
            "api_key": api_key,
            "api_secret": api_secret,
            "testnet": testnet,
        })
        self._name = name
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet

    @property
    def exchange_id(self) -> str:
        return self._name

    def _create_exchange(self) -> ccxt.Exchange:
        exchange_class = getattr(ccxt, self._name)

        config = {
            "enableRateLimit": True,
        }

        if self._api_key:
            config["apiKey"] = self._api_key
        if self._api_secret:
            config["secret"] = self._api_secret
        if self._testnet:
            config["options"] = {"defaultType": "future"}

        return exchange_class(config)
