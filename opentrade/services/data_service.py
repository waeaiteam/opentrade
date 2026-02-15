"""
OpenTrade 数据服务
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional
from decimal import Decimal

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
    
    async def get_market_state(self, symbol: str) -> Optional[MarketState]:
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
    
    async def fetch_ticker(self, symbol: str) -> dict:
        """获取 ticker 数据"""
        exchange = await self._get_exchange()
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
        orderbook = await exchange.fetch_order_book(symbol, limit=limit)
        return {
            "bids": orderbook.get("bids", [])[:limit],
            "asks": orderbook.get("asks", [])[:limit],
        }
    
    async def fetch_funding(self, symbol: str) -> dict:
        """获取资金费率"""
        exchange = await self._get_exchange()
        try:
            funding = await exchange.fetch_funding_rate(symbol)
            return {
                "rate": funding.get("fundingRate", 0),
                "nextTime": funding.get("nextFundingTime"),
            }
        except:
            return {"rate": 0, "nextTime": None}
    
    async def fetch_onchain_data(self, symbol: str) -> dict:
        """获取链上数据 (模拟，实际需要区块链 API)"""
        # 模拟数据
        import random
        return {
            "exchange_net_flow": random.uniform(-1000, 1000),
            "whale_transactions": random.randint(0, 20),
            "stablecoin_mint": random.uniform(-1e8, 1e8),
        }
    
    async def fetch_sentiment_data(self) -> dict:
        """获取情绪数据"""
        import random
        return {
            "fear_greed_index": random.randint(20, 80),
            "social_sentiment": random.uniform(-0.5, 0.5),
            "twitter_volume": random.randint(10000, 100000),
        }
    
    async def fetch_macro_data(self) -> dict:
        """获取宏观数据"""
        return {
            "dxy_index": 103.5,
            "sp500_change": 0.005,
            "gold_price": 2050.0,
            "bond_yield_10y": 4.2,
            "vix_index": 18.5,
        }
    
    def _calculate_indicators(self, ohlcv: list[dict]) -> dict:
        """计算技术指标"""
        if not ohlcv:
            return self._default_indicators()
        
        closes = [d["close"] for d in ohlcv]
        highs = [d["high"] for d in ohlcv]
        lows = [d["low"] for d in ohlcv]
        volumes = [d["volume"] for d in ohlcv]
        
        latest = ohlcv[-1]
        
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
            self._exchanges[self.config.exchange.name] = exchange_class({
                "apiKey": self.config.exchange.api_key,
                "secret": self.config.exchange.api_secret,
                "enableRateLimit": True,
            })
        return self._exchanges[self.config.exchange.name]
    
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
