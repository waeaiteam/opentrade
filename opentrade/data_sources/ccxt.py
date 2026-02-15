"""
OpenTrade Data Sources - CCXT Integration

CCXT 数据源: 支持 100+ 交易所
"""

from datetime import datetime
from typing import Any, AsyncGenerator
from opentrade.data.service import Candle, Tick, Timeframe, DataSource, DataConnector


class CCXTDataSource(DataConnector):
    """CCXT 数据源"""

    def __init__(self):
        super().__init__(DataSource.CCXT)
        self._exchange = None
        self._exchanges = {}

    def connect(self, exchange_id: str, api_key: str = "", api_secret: str = ""):
        """连接交易所"""
        try:
            import ccxt

            exchange_class = getattr(ccxt, exchange_id, None)
            if not exchange_class:
                raise ValueError(f"Exchange not found: {exchange_id}")

            if api_key and api_secret:
                self._exchange = exchange_class({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'enableRateLimit': True,
                })
            else:
                self._exchange = exchange_class({'enableRateLimit': True})

            self._exchanges[exchange_id] = self._exchange
            return True

        except ImportError:
            print("[Data] CCXT not installed")
            return False

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """获取 K线"""
        if not self._exchange:
            return []

        try:
            tf = self._timeframe_to_ccxt(timeframe)
            since = int(start.timestamp() * 1000)

            ohlcv = self._exchange.fetch_ohlcv(symbol, tf, since=since, limit=1000)

            candles = []
            for data in ohlcv:
                ts, o, h, l, c, v = data
                candles.append(Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=datetime.fromtimestamp(ts / 1000),
                    open=o, high=h, low=l, close=c, volume=v,
                ))

            return candles

        except Exception as e:
            print(f"[Data] Failed to fetch candles: {e}")
            return []

    async def fetch_ticker(self, symbol: str) -> Tick | None:
        """获取行情"""
        if not self._exchange:
            return None

        try:
            ticker = self._exchange.fetch_ticker(symbol)
            return Tick(
                symbol=symbol,
                price=ticker.get('last', 0),
                volume=ticker.get('quoteVolume', 0),
                bid=ticker.get('bid', 0),
                ask=ticker.get('ask', 0),
                timestamp=datetime.fromtimestamp(ticker.get('timestamp', 0) / 1000),
                source=DataSource.CCXT,
            )
        except Exception:
            return None

    async def watch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> AsyncGenerator[Candle, None]:
        """WebSocket 订阅 K线"""
        # TODO: 实现 WebSocket 订阅
        pass

    async def watch_ticker(
        self,
        symbol: str,
    ) -> AsyncGenerator[Tick, None]:
        """WebSocket 订阅行情"""
        # TODO: 实现 WebSocket 订阅
        pass

    def _timeframe_to_ccxt(self, timeframe: Timeframe) -> str:
        """时间框架转换"""
        mapping = {
            Timeframe.M1: '1m',
            Timeframe.M5: '5m',
            Timeframe.M15: '15m',
            Timeframe.M30: '30m',
            Timeframe.H1: '1h',
            Timeframe.H4: '4h',
            Timeframe.D1: '1d',
            Timeframe.W1: '1w',
        }
        return mapping.get(timeframe, '1h')

    def get_supported_exchanges(self) -> list[str]:
        """获取支持的交易所列表"""
        import ccxt
        return list(ccxt.exchanges)


def create_ccxt_source(
    exchange: str = "binance",
    api_key: str = "",
    api_secret: str = "",
) -> CCXTDataSource:
    """创建 CCXT 数据源"""
    source = CCXTDataSource()
    source.connect(exchange, api_key, api_secret)
    return source
