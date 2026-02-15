"""
OpenTrade Notifiers - Log Notifier

日志通知器 (写入文件/控制台)
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from opentrade.notifiers import BaseNotifier


class LogNotifier(BaseNotifier):
    """日志通知器"""

    def __init__(
        self,
        log_dir: str = "./data/logs",
        log_level: str = "INFO",
        enabled: bool = True,
    ):
        self.log_dir = Path(log_dir)
        self.log_level = log_level
        self.enabled = enabled
        self.name = "Log"

        # 创建日志目录
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def send_message(self, message: str, **kwargs) -> bool:
        """记录消息"""
        if not self.enabled:
            return False

        self._write_log("INFO", message, kwargs)
        return True

    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        pnl: float | None = None,
        **kwargs,
    ) -> bool:
        """记录交易"""
        if not self.enabled:
            return False

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "TRADE",
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            "pnl": pnl,
            **kwargs,
        }

        self._write_json("trades.log", log_entry)
        self._log_to_console(f"Trade: {side} {quantity} {symbol} @ {price}")

        return True

    async def send_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "INFO",
        **kwargs,
    ) -> bool:
        """记录告警"""
        if not self.enabled:
            return False

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "ALERT",
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
            **kwargs,
        }

        self._write_json("alerts.log", log_entry)
        self._log_to_console(f"Alert [{severity}]: {alert_type} - {message}")

        return True

    async def send_daily_summary(self, stats: dict) -> bool:
        """记录每日汇总"""
        if not self.enabled:
            return False

        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "SUMMARY",
            **stats,
        }

        self._write_json("daily_summaries.log", log_entry)
        self._log_to_console(f"Daily Summary: {json.dumps(stats)}")

        return True

    def _write_log(self, level: str, message: str, extra: dict = None):
        """写入日志行"""
        timestamp = datetime.utcnow().isoformat()
        log_line = f"[{timestamp}] [{level}] {message}"

        if extra:
            log_line += f" | {json.dumps(extra)}"

        log_file = self.log_dir / "opentrade.log"
        with open(log_file, "a") as f:
            f.write(log_line + "\n")

        self._log_to_console(log_line)

    def _write_json(self, filename: str, entry: dict):
        """写入 JSON 日志"""
        log_file = self.log_dir / filename
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _log_to_console(self, message: str):
        """输出到控制台"""
        print(message)


def create_log_notifier(
    log_dir: str = "./data/logs",
    log_level: str = "INFO",
    enabled: bool = True,
) -> LogNotifier:
    """创建日志通知器"""
    return LogNotifier(log_dir=log_dir, log_level=log_level, enabled=enabled)
