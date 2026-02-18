"""
OpenTrade 数据服务
"""

import asyncio
from datetime import datetime

import ccxt.async_support as ccxt

from opentrade.agents.base import MarketState
from opentrade.core.config import get_config


class DataService:
    """数据服务

    负责获取和管理市场数据，
    包括价格、K线、技术指标等。
    """

    _instance: "DataService" = None
    _exchanges: dict[str, ccxt.Exchange] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.config = get_config()
        self._indicators = {}
        self._cache = {}

    async def get_market_state(self, symbol: str) -> MarketState | None:
        """获取市场状态"""
        try:
            # 并行获取数据
            ohlcv_1h, ohlcv_4h, ticker, orderbook, funding = await asyncio.gather(
                self.fetch_ohlcv(symbol, timeframe="1h", limit=100),
                self.fetch_ohlcv(symbol, timeframe="4h", limit=100),
                self.fetch_ticker(symbol),
                self.fetch_orderbook(symbol),
                self.fetch_funding(symbol),
                return_exceptions=True
            )

            if isinstance(ohlcv_1h, Exception):
                return None

            # 计算技术指标
            indicators = self._calculate_indicators(ohlcv_1h)

            # 获取链上数据 (模拟，实际需要 API)
            onchain_data = await self.fetch_onchain_data(symbol)

            # 获取情绪数据 (模拟)
            sentiment = await self.fetch_sentiment_data()

            # 获取宏观数据 (模拟)
            macro = await self.fetch_macro_data()

            # 构建市场状态
            price = ohlcv_1h[-1]["close"] if ohlcv_1h else 0

            state = MarketState(
                symbol=symbol,
                price=price,
                timestamp=datetime.utcnow(),
                ohlcv_1h=self._format_ohlcv(ohlcv_1h),
                ohlcv_4h=self._format_ohlcv(ohlcv_4h),
                orderbook=orderbook or {},
                funding_rate=funding.get("rate", 0) if funding else 0,
                funding_time=funding.get("nextTime"),
                open_interest=ticker.get("openInterest", 0) if ticker else 0,
                open_interest_change=0,  # 需要历史对比
                **indicators,
                **onchain_data,
                **sentiment,
                **macro,
            )

            return state

        except Exception as e:
            print(f"获取市场数据失败: {e}")
            return None

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
    ) -> list[dict]:
        """获取 K 线数据"""
        exchange = await self._get_exchange()

        # 处理 Hyperliquid 交易对格式
        symbol = self._format_symbol_for_exchange(symbol, exchange.id)

        ohlcv = await exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=limit,
        )

        return [
            {
                "timestamp": d[0],
                "open": d[1],
                "high": d[2],
                "low": d[3],
                "close": d[4],
                "volume": d[5],
            }
            for d in ohlcv
        ]

    def _format_symbol_for_exchange(self, symbol: str, exchange_id: str) -> str:
        """格式化交易对以适应不同交易所"""
        # 移除标准后缀
        base_symbol = symbol.replace("/USDT", "").replace("/USD", "").replace("-USD", "").replace("/USDC", "")

        if exchange_id == "hyperliquid":
            # Hyperliquid 使用 BTC/USDC 或 BTC/USDH 格式
            # 优先使用 USDC
            return f"{base_symbol}/USDC"
        elif exchange_id in ["binance", "bybit", "okx"]:
            # 这些交易所使用 BTC/USDT 格式
            return f"{base_symbol}/USDT"
        elif exchange_id == "coinbase":
            # Coinbase 使用 BTC-USD 格式
            return f"{base_symbol}-USD"

        return symbol

    async def fetch_ticker(self, symbol: str) -> dict:
        """获取 ticker 数据"""
        exchange = await self._get_exchange()
        symbol = self._format_symbol_for_exchange(symbol, exchange.id)
        ticker = await exchange.fetch_ticker(symbol)
        return {
            "last": ticker.get("last"),
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "volume": ticker.get("baseVolume"),
            "high": ticker.get("high"),
            "low": ticker.get("low"),
            "openInterest": ticker.get("openInterest"),
        }

    async def fetch_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """获取订单簿"""
        exchange = await self._get_exchange()
        symbol = self._format_symbol_for_exchange(symbol, exchange.id)
        orderbook = await exchange.fetch_order_book(symbol, limit=limit)
        return {
            "bids": orderbook.get("bids", [])[:limit],
            "asks": orderbook.get("asks", [])[:limit],
        }

    async def fetch_funding(self, symbol: str) -> dict:
        """获取资金费率"""
        exchange = await self._get_exchange()
        symbol = self._format_symbol_for_exchange(symbol, exchange.id)
        try:
            funding = await exchange.fetch_funding_rate(symbol)
            return {
                "rate": funding.get("fundingRate", 0),
                "nextTime": funding.get("nextFundingTime"),
            }
        except Exception:
            return {"rate": 0, "nextTime": None}

    async def fetch_balance(self) -> dict:
        """获取账户余额"""
        exchange = await self._get_exchange()
        params = self._get_user_params()
        try:
            balance = await exchange.fetch_balance(params=params)
            return {
                "total": balance.get("total", {}),
                "free": balance.get("free", {}),
                "used": balance.get("used", {}),
            }
        except Exception as e:
            print(f"获取余额失败: {e}")
            return {"total": {}, "free": {}, "used": {}}

    async def fetch_onchain_data(self, symbol: str) -> dict:
        """获取链上数据"""
        # 尝试从 DeFi Llama 获取
        try:
            import aiohttp
            base = symbol.replace("/USDT", "").replace("/USDC", "")
            
            async with aiohttp.ClientSession() as session:
                # 获取 ETH 链上数据
                if base == "ETH":
                    async with session.get(
                        "https://api.llama.fi/summary/flows/ethereum",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            total = data.get("total", 0)
                            return {
                                "exchange_net_flow": total,
                                "whale_transactions": 0,  # 需要专门API
                                "stablecoin_mint": 0,  # 需要Tether/Binance API
                            }
        except Exception:
            pass
        
        # 默认返回估算值
        return {
            "exchange_net_flow": 0,
            "whale_transactions": 0,
            "stablecoin_mint": 0,
        }

    async def fetch_sentiment_data(self) -> dict:
        """获取情绪数据"""
        # 尝试获取 Fear & Greed Index
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.alternative.me/fng/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            fng = int(data["data"][0]["value"])
                            classification = data["data"][0]["value_classification"]
                            return {
                                "fear_greed_index": fng,
                                "fear_greed_class": classification,
                                "twitter_sentiment": 0,  # 需要 Twitter API
                                "news_sentiment": 0,  # 需要 News API
                            }
        except Exception:
            pass
        
        # 默认返回中性值
        return {
            "fear_greed_index": 50,
            "fear_greed_class": "neutral",
            "twitter_sentiment": 0,
            "news_sentiment": 0,
        }

    async def fetch_macro_data(self) -> dict:
        """获取宏观数据"""
        # 尝试从 Yahoo Finance 获取
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # 简化：返回估算值
                # 实际应该使用 yfinance 或专门的 API
                return {
                    "dxy_index": 103.5,  # 美元指数
                    "sp500_change": 0.005,
                    "gold_price": 2050.0,
                    "bond_yield_10y": 4.2,
                    "vix_index": 18.5,
                }
        except Exception:
            pass
        
        return {
            "dxy_index": 100,
            "sp500_change": 0,
            "gold_price": 2000,
            "bond_yield_10y": 4.0,
            "vix_index": 20,
        }

    def _calculate_indicators(self, ohlcv: list[dict]) -> dict:
        """计算技术指标"""
        if not ohlcv:
            return self._default_indicators()

        closes = [d["close"] for d in ohlcv]
        _highs = [d["high"] for d in ohlcv]
        _lows = [d["low"] for d in ohlcv]
        volumes = [d["volume"] for d in ohlcv]

        _latest = ohlcv[-1]

        # EMA
        ema_fast = self._ema(closes, 9)
        ema_slow = self._ema(closes, 21)

        # RSI
        rsi = self._rsi(closes, 14)

        # MACD
        macd, macd_signal, macd_hist = self._macd(closes, 12, 26, 9)

        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self._bollinger_bands(closes, 20, 2)

        # ATR
        atr = self._atr(ohlcv, 14)

        # 成交量分析
        vol_ma = self._sma(volumes, 20)
        vol_ratio = volumes[-1] / vol_ma if vol_ma > 0 else 1.0

        return {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_histogram": macd_hist,
            "bollinger_upper": bb_upper,
            "bollinger_middle": bb_middle,
            "bollinger_lower": bb_lower,
            "atr": atr,
            "volume": volumes[-1],
            "volume_ratio": vol_ratio,
        }

    def _default_indicators(self) -> dict:
        """默认指标值"""
        return {
            "ema_fast": 0,
            "ema_slow": 0,
            "rsi": 50,
            "macd": 0,
            "macd_signal": 0,
            "macd_histogram": 0,
            "bollinger_upper": 0,
            "bollinger_middle": 0,
            "bollinger_lower": 0,
            "atr": 0,
            "volume": 0,
            "volume_ratio": 1.0,
        }

    def _format_ohlcv(self, ohlcv: list[dict]) -> dict:
        """格式化 K 线数据"""
        if not ohlcv:
            return {}
        return {
            "open": ohlcv[-1]["open"],
            "high": ohlcv[-1]["high"],
            "low": ohlcv[-1]["low"],
            "close": ohlcv[-1]["close"],
            "volume": ohlcv[-1]["volume"],
        }

    async def _get_exchange(self) -> ccxt.Exchange:
        """获取交易所实例"""
        if self.config.exchange.name not in self._exchanges:
            exchange_class = getattr(ccxt, self.config.exchange.name)
            
            # Hyperliquid 需要额外的 wallet 参数
            options = {
                "apiKey": self.config.exchange.api_key,
                "enableRateLimit": True,
            }
            
            if self.config.exchange.name == "hyperliquid":
                options["wallet"] = self.config.exchange.wallet_address
            
            self._exchanges[self.config.exchange.name] = exchange_class(options)
        return self._exchanges[self.config.exchange.name]

    def _get_user_params(self) -> dict:
        """获取用户参数（用于 Hyperliquid API）"""
        if self.config.exchange.name == "hyperliquid":
            return {"user": self.config.exchange.wallet_address}
        return {}

    async def close(self):
        """关闭所有交易所连接"""
        for exchange in self._exchanges.values():
            try:
                await exchange.close()
            except Exception:
                pass
        self._exchanges.clear()

    # 技术指标计算
    def _ema(self, data: list, period: int) -> float:
        """指数移动平均"""
        if len(data) < period:
            return data[-1] if data else 0

        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = price * multiplier + ema * (1 - multiplier)
        return ema

    def _sma(self, data: list, period: int) -> float:
        """简单移动平均"""
        if len(data) < period:
            return sum(data) / len(data) if data else 0
        return sum(data[-period:]) / period

    def _rsi(self, data: list, period: int) -> float:
        """相对强弱指数"""
        if len(data) < period + 1:
            return 50

        gains = []
        losses = []
        for i in range(1, len(data)):
            change = data[i] - data[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _macd(self, data: list, fast: int, slow: int, signal: int):
        """MACD"""
        ema_fast = self._ema(data, fast)
        ema_slow = self._ema(data, slow)
        macd_line = ema_fast - ema_slow

        # Signal line
        signal_ema_data = []
        for i in range(slow, len(data)):
            signal_ema_data.append(self._ema(data[:i+1], signal))
        signal_line = signal_ema_data[-1] if signal_ema_data else 0

        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def _bollinger_bands(self, data: list, period: int, std_dev: int):
        """布林带"""
        if len(data) < period:
            return 0, 0, 0

        sma = self._sma(data, period)
        std = self._std(data[-period:], period)

        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)

        return upper, sma, lower

    def _std(self, data: list, period: int) -> float:
        """标准差"""
        if len(data) < 2:
            return 0
        mean = sum(data) / len(data)
        variance = sum((x - mean) ** 2 for x in data) / len(data)
        return variance ** 0.5

    def _atr(self, ohlcv: list[dict], period: int) -> float:
        """平均真实波幅"""
        if len(ohlcv) < period + 1:
            return 0

        trs = []
        for i in range(1, len(ohlcv)):
            high = ohlcv[i]["high"]
            low = ohlcv[i]["low"]
            prev_close = ohlcv[i - 1]["close"]

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)

        return sum(trs[-period:]) / period if trs else 0


# 全局数据服务实例
data_service = DataService()
