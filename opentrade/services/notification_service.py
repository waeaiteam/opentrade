"""
OpenTrade 通知服务
"""

import asyncio
from datetime import datetime

from opentrade.core.config import get_config


class NotificationService:
    """通知服务
    
    负责发送各种通知，
    包括 Telegram、邮件、Push 等。
    """

    def __init__(self):
        self.config = get_config()
        self._telegram_lock = asyncio.Lock()
        self._email_lock = asyncio.Lock()

    async def send_trade_notification(
        self,
        action: str,
        symbol: str,
        price: float,
        quantity: float,
        pnl: float = None,
        mode: str = "paper",
    ):
        """发送交易通知"""
        emoji = "🟢" if action in ["BUY", "LONG"] else ("🔴" if action in ["SELL", "SHORT", "CLOSE"] else "⚪")
        mode_emoji = "💰 实盘" if mode == "live" else "📝 模拟"

        message = f"""
{emoji} {mode_emoji} 交易信号

📌 动作: {action}
💎 标的: {symbol}
💵 价格: ${price:,.2f}
📊 数量: {quantity:.4f}
"""

        if pnl is not None:
            pnl_emoji = "✅" if pnl > 0 else "❌"
            message += f"{pnl_emoji} 盈亏: ${pnl:+,.2f}"

        await self._send_all(message)

    async def send_alert(
        self,
        level: str,
        title: str,
        message: str,
    ):
        """发送告警"""
        level_emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "🚨",
            "critical": "🔴",
        }.get(level, "📢")

        full_message = f"""
{level_emoji} {title.upper()}

{message}
"""

        await self._send_all(full_message)

    async def send_daily_summary(
        self,
        total_pnl: float,
        win_rate: float,
        trades_count: int,
        balance: float,
    ):
        """发送每日总结"""
        pnl_emoji = "📈" if total_pnl > 0 else "📉"

        message = f"""
📊 每日交易总结

{pnl_emoji} 总盈亏: ${total_pnl:+,.2f}
🎯 胜率: {win_rate:.1%}
📝 交易次数: {trades_count}
💰 当前余额: ${balance:,.2f}

时间: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
"""

        await self._send_all(message)

    async def send_strategy_update(
        self,
        strategy_name: str,
        old_version: str,
        new_version: str,
        changes: str,
    ):
        """发送策略更新通知"""
        message = f"""
🔄 策略更新

📌 策略: {strategy_name}
📝 {old_version} → {new_version}

变更: {changes}
"""

        await self._send_all(message)

    async def send_error(
        self,
        error: str,
        context: str = None,
    ):
        """发送错误通知"""
        message = f"""
🚨 系统错误

❌ 错误: {error}
"""

        if context:
            message += f"\n📋 上下文: {context}"

        await self._send_all(message)

    async def _send_all(self, message: str):
        """发送所有渠道"""
        tasks = []

        if self.config.notification.telegram_enabled:
            tasks.append(self._send_telegram(message))

        if self.config.notification.email_enabled:
            tasks.append(self._send_email(message))

        if self.config.notification.push_enabled:
            tasks.append(self._send_push(message))

        # 并发发送
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_telegram(self, message: str):
        """发送 Telegram 消息"""
        async with self._telegram_lock:
            try:
                import httpx

                token = self.config.notification.telegram_bot_token
                chat_id = self.config.notification.telegram_chat_id

                if not token or not chat_id:
                    return

                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": message,
                            "parse_mode": "Markdown",
                        },
                        timeout=10,
                    )

            except Exception as e:
                print(f"Telegram 发送失败: {e}")

    async def _send_email(self, message: str):
        """发送邮件"""
        async with self._email_lock:
            try:
                from email.mime.text import MIMEText

                import aiosmtplib

                smtp_host = self.config.notification.email_smtp_host
                smtp_port = self.config.notification.email_smtp_port
                from_addr = self.config.notification.email_from
                to_addr = self.config.notification.email_to

                if not all([smtp_host, smtp_port, from_addr, to_addr]):
                    return

                msg = MIMEText(message, "plain", "utf-8")
                msg["Subject"] = "OpenTrade 通知"
                msg["From"] = from_addr
                msg["To"] = to_addr

                await aiosmtplib.send(
                    msg,
                    hostname=smtp_host,
                    port=smtp_port,
                    use_tls=True,
                )

            except Exception as e:
                print(f"邮件发送失败: {e}")

    async def _send_push(self, message: str):
        """发送 Push 通知"""
        # TODO: 实现 Push 通知
        print(f"Push 通知: {message}")

    async def test_telegram(self) -> bool:
        """测试 Telegram 配置"""
        test_message = "✅ OpenTrade Telegram 通知测试成功！"

        try:
            await self._send_telegram(test_message)
            return True
        except Exception as e:
            print(f"Telegram 测试失败: {e}")
            return False


# 全局通知服务实例
notification_service = NotificationService()
