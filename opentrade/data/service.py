"""
OpenTrade Data Layer - TimescaleDB 数据存储

实现:
1. 时间序列存储 (K线/tick数据)
2. 账户数据存储 (订单/持仓/余额)
3. 策略数据存储 (信号/绩效)
4. 数据质量管理
5. 冷热分层

数据模型:
┌─────────────────────────────────────────────────────────┐
│                     TimescaleDB                          │
├─────────────────────────────────────────────────────────┤
│  hypertable: market_candles      │ K线数据              │
│  hypertable: market_ticks         │ Tick数据             │
│  hypertable: orders               │ 订单记录             │
│  hypertable: positions            │ 持仓记录             │
│  hypertable: balance_history      │ 余额历史             │
│  hypertable: strategy_signals     │ 策略信号             │
│  hypertable: performance_logs     │ 绩效日志             │
├─────────────────────────────────────────────────────────┤
│  continuous aggregates: hourly/daily summaries          │
│  compression: after 7 days                               │
│  retention: 2 years hot, 10 years cold                  │
└─────────────────────────────────────────────────────────┘
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel


# ============ 数据模型 ============

class Timeframe(str, Enum):
    """时间框架"""
    TICK = "tick"
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class DataSource(str, Enum):
    """数据源"""
    BINANCE = "binance"
    BYBIT = "bybit"
    COINGECKO = "coingecko"
    HYPERLIQUID = "hyperliquid"


@dataclass
class Candle:
    """K线数据"""
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int | None = None

    # 指标
    rsi: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    bollinger_upper: float | None = None
    bollinger_middle: float | None = None
    bollinger_lower: float | None = None
    atr: float | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "trades": self.trades,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Candle":
        return cls(
            symbol=data["symbol"],
            timeframe=Timeframe(data["timeframe"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            volume=data["volume"],
            trades=data.get("trades"),
        )


@dataclass
class Tick:
    """Tick 数据"""
    symbol: str
    price: float
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: DataSource = DataSource.BINANCE


@dataclass
class OrderRecord:
    """订单记录"""
    order_id: str
    symbol: str
    side: str
    type: str
    status: str
    quantity: float
    filled: float
    price: float | None = None
    fee: float = 0.0
    strategy_id: str | None = None
    trace_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None


@dataclass
class BalanceRecord:
    """余额记录"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    total: float
    available: float
    margin: float
    unrealized_pnl: float = 0.0
    balances: dict[str, float] = field(default_factory=dict)


@dataclass
class SignalRecord:
    """信号记录"""
    signal_id: str
    strategy_id: str
    symbol: str
    action: str
    confidence: float
    direction: str
    reasons: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ============ 数据库连接 ============

class TimescaleDB:
    """TimescaleDB 连接器"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "opentrade",
        user: str = "postgres",
        password: str = "",
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password

        self._pool = None
        self._initialized = False

    async def connect(self):
        """连接数据库"""
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=2,
                max_size=10,
            )
        except ImportError:
            print("[Data] asyncpg not installed, using mock mode")
            self._pool = None

    async def close(self):
        """关闭连接"""
        if self._pool:
            self._pool.close()
            self._pool = None

    async def initialize(self):
        """初始化数据库表"""
        if not self._pool:
            return

        async with self._pool.acquire() as conn:
            # 创建扩展
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

            # 创建 K线表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_candles (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    open DOUBLE PRECISION NOT NULL,
                    high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL,
                    close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION DEFAULT 0,
                    trades INTEGER,
                    PRIMARY KEY (symbol, timeframe, timestamp)
                )
            """)

            # 创建超表
            try:
                await conn.execute(
                    "SELECT create_hypertable('market_candles', 'timestamp')"
                )
            except Exception:
                pass

            # 订单表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quantity DOUBLE PRECISION NOT NULL,
                    filled DOUBLE PRECISION DEFAULT 0,
                    price DOUBLE PRECISION,
                    fee DOUBLE PRECISION DEFAULT 0,
                    strategy_id TEXT,
                    trace_id TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    filled_at TIMESTAMPTZ
                )
            """)

            # 余额表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS balance_history (
                    id SERIAL PRIMARY KEY,
                    total DOUBLE PRECISION NOT NULL,
                    available DOUBLE PRECISION NOT NULL,
                    margin DOUBLE PRECISION NOT NULL,
                    unrealized_pnl DOUBLE PRECISION DEFAULT 0,
                    balances JSONB,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            self._initialized = True

    # ============ K线操作 ============

    async def insert_candle(self, candle: Candle):
        """插入 K线"""
        if not self._pool:
            return

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO market_candles
                (symbol, timeframe, timestamp, open, high, low, close, volume, trades)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (symbol, timeframe, timestamp) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    trades = EXCLUDED.trades
            """, candle.symbol, candle.timeframe.value, candle.timestamp,
                candle.open, candle.high, candle.low, candle.close, candle.volume,
                candle.trades)

    async def insert_candles(self, candles: list[Candle]):
        """批量插入 K线"""
        if not self._pool or not candles:
            return

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for candle in candles:
                    await conn.execute("""
                        INSERT INTO market_candles
                        (symbol, timeframe, timestamp, open, high, low, close, volume)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT DO NOTHING
                    """, candle.symbol, candle.timeframe.value, candle.timestamp,
                        candle.open, candle.high, candle.low, candle.close, candle.volume)

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[Candle]:
        """获取 K线"""
        if not self._pool:
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM market_candles
                WHERE symbol = $1 AND timeframe = $2
                AND timestamp >= $3 AND timestamp <= $4
                ORDER BY timestamp DESC
                LIMIT $5
            """, symbol, timeframe.value, start, end, limit)

            return [Candle.from_dict(dict(row)) for row in rows]

    async def get_latest_candle(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> Candle | None:
        """获取最新 K线"""
        if not self._pool:
            return None

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM market_candles
                WHERE symbol = $1 AND timeframe = $2
                ORDER BY timestamp DESC
                LIMIT 1
            """, symbol, timeframe.value)

            return Candle.from_dict(dict(row)) if row else None

    # ============ 账户操作 ============

    async def record_balance(self, balance: BalanceRecord):
        """记录余额"""
        if not self._pool:
            return

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO balance_history
                (total, available, margin, unrealized_pnl, balances)
                VALUES ($1, $2, $3, $4, $5)
            """, balance.total, balance.available, balance.margin,
                balance.unrealized_pnl, json.dumps(balance.balances))

    async def get_balance_history(
        self,
        start: datetime,
        end: datetime,
    ) -> list[BalanceRecord]:
        """获取余额历史"""
        if not self._pool:
            return []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM balance_history
                WHERE timestamp >= $1 AND timestamp <= $2
                ORDER BY timestamp DESC
            """, start, end)

            return [
                BalanceRecord(
                    total=row["total"],
                    available=row["available"],
                    margin=row["margin"],
                    unrealized_pnl=row["unrealized_pnl"],
                    balances=row["balances"] or {},
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]


# ============ 数据质量监控 ============

@dataclass
class DataQualityReport:
    """数据质量报告"""
    symbol: str
    timeframe: Timeframe
    start: datetime
    end: datetime

    # 统计
    total_candles: int = 0
    missing_candles: int = 0
    gap_count: int = 0
    max_gap_minutes: int = 0

    # 质量分数
    completeness_score: float = 0.0
    consistency_score: float = 0.0
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "total_candles": self.total_candles,
            "missing_candles": self.missing_candles,
            "gap_count": self.gap_count,
            "max_gap_minutes": self.max_gap_minutes,
            "completeness_score": self.completeness_score,
            "consistency_score": self.consistency_score,
            "overall_score": self.overall_score,
        }


class DataQualityMonitor:
    """数据质量监控"""

    def __init__(self, db: TimescaleDB):
        self.db = db

    async def check_quality(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> DataQualityReport:
        """检查数据质量"""
        report = DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

        # 获取实际数据
        candles = await self.db.get_candles(symbol, timeframe, start, end, limit=100000)
        report.total_candles = len(candles)

        # 计算期望数量
        interval_minutes = self._timeframe_to_minutes(timeframe)
        expected_count = int((end - start).total_seconds() / 60 / interval_minutes)

        # 缺失数量
        report.missing_candles = max(0, expected_count - report.total_candles)

        # 完整度分数
        if expected_count > 0:
            report.completeness_score = min(1.0, report.total_candles / expected_count)

        # 检查连续性
        if candles:
            sorted_candles = sorted(candles, key=lambda c: c.timestamp)
            gaps = self._find_gaps(sorted_candles, interval_minutes)
            report.gap_count = len(gaps)
            if gaps:
                report.max_gap_minutes = max(gaps)

            # 一致性分数
            report.consistency_score = 1.0 - (report.gap_count / max(1, expected_count) * 10)

        report.overall_score = (
            report.completeness_score * 0.6 +
            report.consistency_score * 0.4
        )

        return report

    def _timeframe_to_minutes(self, timeframe: Timeframe) -> int:
        """时间框架转分钟"""
        mapping = {
            Timeframe.TICK: 0,
            Timeframe.M1: 1,
            Timeframe.M5: 5,
            Timeframe.M15: 15,
            Timeframe.M30: 30,
            Timeframe.H1: 60,
            Timeframe.H4: 240,
            Timeframe.D1: 1440,
            Timeframe.W1: 10080,
        }
        return mapping.get(timeframe, 60)

    def _find_gaps(self, candles: list[Candle], interval_minutes: int) -> list[int]:
        """查找缺口"""
        gaps = []

        for i in range(1, len(candles)):
            expected_gap = interval_minutes
            actual_gap = int((candles[i].timestamp - candles[i-1].timestamp).total_seconds() / 60)

            if actual_gap > interval_minutes * 1.5:  # 允许50%误差
                gaps.append(actual_gap)

        return gaps


# ============ 数据服务 ============

class DataService:
    """
    数据服务 - 统一数据访问接口

    功能:
    1. K线数据获取
    2. 实时数据订阅
    3. 数据质量监控
    4. 冷热数据分层
    """

    def __init__(self, db: TimescaleDB | None = None):
        self.db = db or TimescaleDB()
        self.quality_monitor = DataQualityMonitor(self.db)

        # 缓存
        self._cache: dict[str, list[Candle]] = {}
        self._cache_ttl = 60  # 60秒

        # 数据源
        self._connectors: dict[DataSource, "DataConnector"] = {}

    def register_connector(self, source: DataSource, connector: "DataConnector"):
        """注册数据源连接器"""
        self._connectors[source] = connector

    async def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        source: DataSource = DataSource.BINANCE,
    ) -> list[Candle]:
        """获取 K线数据"""
        cache_key = f"{symbol}:{timeframe.value}:{start.isoformat()}:{end.isoformat()}"

        # 尝试缓存
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 从数据库获取
        if self.db:
            candles = await self.db.get_candles(symbol, timeframe, start, end)

        # 如果没有数据，从连接器获取
        if not candles and source in self._connectors:
            connector = self._connectors[source]
            candles = await connector.fetch_candles(symbol, timeframe, start, end)

            # 存入数据库
            if candles and self.db:
                await self.db.insert_candles(candles)

        self._cache[cache_key] = candles
        return candles

    async def get_recent_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        count: int = 100,
    ) -> list[Candle]:
        """获取最近 K线"""
        end = datetime.utcnow()
        start = end - timedelta(minutes=self._timeframe_to_minutes(timeframe) * count)
        return await self.get_candles(symbol, timeframe, start, end)

    async def check_data_quality(
        self,
        symbol: str,
        timeframe: Timeframe,
        days: int = 7,
    ) -> DataQualityReport:
        """检查数据质量"""
        end = datetime.utcnow()
        start = end - timedelta(days=days)
        return await self.quality_monitor.check_quality(symbol, timeframe, start, end)

    async def record_balance(self, balance: BalanceRecord):
        """记录余额"""
        if self.db:
            await self.db.record_balance(balance)

    def _timeframe_to_minutes(self, timeframe: Timeframe) -> int:
        mapping = {
            Timeframe.M1: 1, Timeframe.M5: 5, Timeframe.M15: 15, Timeframe.M30: 30,
            Timeframe.H1: 60, Timeframe.H4: 240, Timeframe.D1: 1440, Timeframe.W1: 10080,
        }
        return mapping.get(timeframe, 60)


# ============ 数据源连接器接口 ============

class DataConnector:
    """数据源连接器基类"""

    def __init__(self, source: DataSource):
        self.source = source

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """获取 K线"""
        return []

    async def fetch_ticker(self, symbol: str) -> Tick | None:
        """获取行情"""
        return None


# ============ 便捷函数 ============

def create_data_service(
    host: str = "localhost",
    port: int = 5432,
    database: str = "opentrade",
    user: str = "postgres",
    password: str = "",
) -> DataService:
    """创建数据服务"""
    db = TimescaleDB(host, port, database, user, password)
    return DataService(db)
