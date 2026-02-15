"""
OpenTrade 数据质量服务 - P0 优化

核心优化: 数据时序对齐与质量校验
- 统一时间戳基准
- 数据质量校验流水线
- 不可变原始数据层

作者: OpenTrade AI
日期: 2026-02-15
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ============== 数据校验结果 ==============

@dataclass
class DataValidationResult:
    """数据校验结果"""
    is_valid: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    corrected_values: dict = field(default_factory=dict)

    def add_error(self, error: str):
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: str):
        self.warnings.append(warning)


@dataclass
class MarketDataPoint:
    """标准化市场数据点"""
    symbol: str
    timestamp: int  # 毫秒级 UTC
    open: float
    high: float
    low: float
    close: float
    volume: float

    # 质量标记
    is_valid: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_valid": self.is_valid,
            "errors": self.validation_errors,
        }


# ============== 数据质量流水线 ==============

class DataQualityPipeline:
    """
    数据质量校验流水线
    
    三重校验:
    1. 完整性校验
    2. 一致性校验
    3. 延迟校验
    """

    def __init__(self):
        self._thresholds = {
            "price_deviation_pct": 0.05,      # 价格偏差阈值 5%
            "volume_zero_pct": 0.01,          # 零成交量阈值 1%
            "ohlc_invalid_pct": 0.001,        # 无效OHLC阈值 0.1%
            "max_delay_ms": 100,              # 最大延迟 100ms
            "duplicate_timestamp_window_ms": 1000,  # 重复时间戳窗口 1s
        }

    def validate_ohlcv(self, data: dict) -> DataValidationResult:
        """
        完整性校验
        
        检查:
        - OHLCV 字段完整
        - 无 0 值 / 异常值
        - 最高价 >= 最低价
        """
        result = DataValidationResult(is_valid=True)

        required_fields = ["open", "high", "low", "close", "volume"]

        for field_name in required_fields:
            if field_name not in data:
                result.add_error(f"缺少字段: {field_name}")
                continue

            value = data[field_name]

            # 检查 0 值
            if field_name != "volume" and value == 0:
                result.add_error(f"{field_name} 为 0")

            # 检查负值
            if value < 0:
                result.add_error(f"{field_name} 为负数: {value}")

        # 检查价格关系
        open_price = data.get("open", 0)
        high_price = data.get("high", 0)
        low_price = data.get("low", 0)
        close_price = data.get("close", 0)

        if high_price < low_price:
            result.add_error(f"最高价 < 最低价: {high_price} < {low_price}")

        if high_price < open_price or high_price < close_price:
            result.add_warning("最高价低于开/收盘价")

        if low_price > open_price or low_price > close_price:
            result.add_warning("最低价高于开/收盘价")

        return result

    def cross_validate_exchange(
        self,
        data: dict,
        reference_data: dict = None,
        symbol: str = "BTC/USDT"
    ) -> DataValidationResult:
        """
        一致性校验
        
        交叉验证多交易所同品种价格
        偏差超阈值触发告警
        """
        result = DataValidationResult(is_valid=True)

        if not reference_data:
            # 无参考数据，跳过
            return result

        our_price = data.get("close", 0)
        ref_price = reference_data.get("close", 0)

        if our_price == 0 or ref_price == 0:
            return result

        deviation = abs(our_price - ref_price) / ref_price

        if deviation > self._thresholds["price_deviation_pct"]:
            result.add_warning(
                f"价格偏差过大: {deviation:.2%} (我们的: {our_price}, 参考: {ref_price})"
            )

        return result

    def validate_latency(self, timestamp: int, max_delay_ms: int = None) -> DataValidationResult:
        """
        延迟校验
        
        行情数据延迟超阈值触发告警
        """
        result = DataValidationResult(is_valid=True)

        max_delay = max_delay_ms or self._thresholds["max_delay_ms"]

        now_ms = int(datetime.utcnow().timestamp() * 1000)
        delay_ms = now_ms - timestamp

        if delay_ms > max_delay:
            result.add_warning(f"数据延迟: {delay_ms}ms > {max_delay}ms")

        # 检查时间戳是否在未来
        if timestamp > now_ms + 1000:  # 1秒容差
            result.add_error(f"时间戳在未来: {timestamp} > {now_ms}")

        return result

    def validate_and_correct(
        self,
        data: dict,
        symbol: str,
        timestamp: int = None
    ) -> tuple[MarketDataPoint, DataValidationResult]:
        """
        完整校验 + 自动修正
        
        Returns:
            (标准化的数据点, 校验结果)
        """
        # 1. 完整性校验
        integrity_result = self.validate_ohlcv(data)

        # 2. 延迟校验
        latency_result = self.validate_latency(timestamp)

        # 3. 合并结果
        result = DataValidationResult(
            is_valid=integrity_result.is_valid,
            errors=integrity_result.errors + latency_result.errors,
            warnings=integrity_result.warnings + latency_result.warnings,
        )

        # 4. 自动修正
        corrected = data.copy()

        # 修正价格关系
        if "high" in corrected and "low" in corrected:
            if corrected["high"] < corrected["low"]:
                corrected["high"] = corrected["low"]
                result.corrected_values["high"] = corrected["high"]
                result.add_warning("已修正: high < low")

        # 5. 创建标准化数据点
        point = MarketDataPoint(
            symbol=symbol,
            timestamp=timestamp or int(datetime.utcnow().timestamp() * 1000),
            open=corrected.get("open", 0),
            high=corrected.get("high", 0),
            low=corrected.get("low", 0),
            close=corrected.get("close", 0),
            volume=corrected.get("volume", 0),
            is_valid=len(result.errors) == 0,
            validation_errors=result.errors,
        )

        return point, result


# ============== 数据时间对齐 ==============

class TimeSeriesAligner:
    """
    时间序列对齐器
    
    将多源数据统一到固定时间窗口
    """

    def __init__(self, timeframe_ms: int = 60000):  # 默认1分钟
        self.timeframe_ms = timeframe_ms

    def align_timestamp(self, timestamp_ms: int) -> int:
        """
        将时间戳对齐到时间窗口
        
        Example:
            timeframe = 1min (60000ms)
            12:03:45 -> 12:03:00
            12:04:15 -> 12:04:00
        """
        return (timestamp_ms // self.timeframe_ms) * self.timeframe_ms

    def align_to_interval(
        self,
        data_points: list[dict],
        interval_minutes: int = 1
    ) -> dict[int, list[dict]]:
        """
        将数据点按时间间隔分组
        
        Returns:
            {aligned_timestamp: [data_points]}
        """
        interval_ms = interval_minutes * 60 * 1000
        aligned = {}

        for point in data_points:
            ts = point.get("timestamp", 0)
            aligned_ts = (ts // interval_ms) * interval_ms

            if aligned_ts not in aligned:
                aligned[aligned_ts] = []
            aligned[aligned_ts].append(point)

        return aligned


# ============== 实时数据质量监控 ==============

class DataQualityMonitor:
    """
    实时数据质量监控
    """

    def __init__(self):
        self._stats = {
            "total_points": 0,
            "valid_points": 0,
            "invalid_points": 0,
            "errors": [],
            "warnings": [],
            "last_update": None,
        }

        self._pipeline = DataQualityPipeline()
        self._alerter = None  # 告警回调

    def set_alert_callback(self, callback: callable):
        """设置告警回调"""
        self._alerter = callback

    async def process_data_point(
        self,
        data: dict,
        symbol: str,
        timestamp: int = None
    ) -> MarketDataPoint:
        """处理单个数据点"""
        self._stats["total_points"] += 1
        self._stats["last_update"] = datetime.utcnow()

        point, result = self._pipeline.validate_and_correct(
            data, symbol, timestamp
        )

        if point.is_valid:
            self._stats["valid_points"] += 1
        else:
            self._stats["invalid_points"] += 1
            self._stats["errors"].extend(result.errors)

        if result.warnings:
            self._stats["warnings"].extend(result.warnings)

            # 触发告警
            if self._alerter and len(result.warnings) > 3:
                await self._alerter(
                    level="warning",
                    message=f"数据质量警告: {len(result.warnings)} 个问题",
                    details=result.warnings
                )

        # 保持统计数量
        self._stats["errors"] = self._stats["errors"][-100:]
        self._stats["warnings"] = self._stats["warnings"][-100:]

        return point

    def get_stats(self) -> dict:
        """获取统计"""
        total = self._stats["total_points"]
        return {
            "total_points": total,
            "valid_points": self._stats["valid_points"],
            "invalid_points": self._stats["invalid_points"],
            "valid_rate": self._stats["valid_points"] / max(total, 1),
            "error_count": len(set(self._stats["errors"])),
            "warning_count": len(set(self._stats["warnings"])),
            "last_update": self._stats["last_update"].isoformat() if self._stats["last_update"] else None,
        }


# ============== 数据湖接口 ==============

class DataLakeLayer:
    """
    数据湖层 - 不可变原始数据
    
    raw 层: 只读不可修改
    processed 层: 清洗、特征工程
    """

    def __init__(self, raw_dir: str = "~/.opentrade/data/raw",
                 processed_dir: str = "~/.opentrade/data/processed"):
        from pathlib import Path

        self.raw_dir = Path(raw_dir).expanduser()
        self.processed_dir = Path(processed_dir).expanduser()

        # 创建目录
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def save_raw(self, symbol: str, data: dict):
        """
        保存原始数据 (追加模式)
        
        格式: {symbol}/{year}/{month}/{day}/{timestamp}.json
        """

        now = datetime.utcnow()
        ts = data.get("timestamp", now.timestamp() * 1000)
        dt = datetime.fromtimestamp(ts / 1000)

        dir_path = self.raw_dir / symbol / str(dt.year) / f"{dt.month:02d}" / f"{dt.day:02d}"
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / f"{int(ts)}.json"

        # 追加写入 (JSONL 格式)
        with open(file_path, "a") as f:
            f.write(json.dumps(data) + "\n")

    def load_raw(self, symbol: str,
                 start_ts: int,
                 end_ts: int) -> list[dict]:
        """加载原始数据 (只读)"""

        results = []

        # 遍历日期范围
        start_dt = datetime.fromtimestamp(start_ts / 1000)
        end_dt = datetime.fromtimestamp(end_ts / 1000)
        current = start_dt

        while current <= end_dt:
            dir_path = self.raw_dir / symbol / str(current.year) / f"{current.month:02d}" / f"{current.day:02d}"

            if dir_path.exists():
                for file_path in dir_path.glob("*.json"):
                    with open(file_path) as f:
                        for line in f:
                            data = json.loads(line)
                            ts = data.get("timestamp", 0)
                            if start_ts <= ts <= end_ts:
                                results.append(data)

            current += timedelta(days=1)

        return sorted(results, key=lambda x: x.get("timestamp", 0))

    def save_processed(self, symbol: str, data: list[dict]):
        """保存处理后的数据"""

        now = datetime.utcnow()
        dir_path = self.processed_dir / symbol / str(now.year) / f"{now.month:02d}"
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / f"{int(now.timestamp())}.json"

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)


# ============== 全局实例 ==============

data_quality_monitor = DataQualityMonitor()
data_lake = DataLakeLayer()
time_series_aligner = TimeSeriesAligner()
