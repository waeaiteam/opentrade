"""
网络异常处理模块
超时保护、重试机制、悬挂订单处理
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any, Dict
from pathlib import Path
import json
import random

logger = logging.getLogger(__name__)


class NetworkErrorType(Enum):
    """网络错误类型"""
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


@dataclass
class NetworkConfig:
    """网络配置"""
    # 超时设置
    default_timeout_seconds: float = 30.0
    order_timeout_seconds: float = 60.0
    heartbeat_interval_seconds: float = 5.0
    
    # 重试设置
    max_retries: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    
    # 限流设置
    requests_per_minute: int = 60
    burst_limit: int = 10
    
    # 悬挂订单
    hanging_order_cleanup_interval_seconds: float = 300  # 5分钟
    hanging_order_threshold_seconds: float = 1800  # 30分钟


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_errors: tuple = (TimeoutError, ConnectionError, OSError)


class NetworkException(Exception):
    """网络异常"""
    
    def __init__(self, error_type: NetworkErrorType, message: str, retry_after: Optional[float] = None):
        self.error_type = error_type
        self.message = message
        self.retry_after = retry_after
        super().__init__(message)


class NetworkHandler:
    """
    网络异常处理器
    
    功能:
    1. 超时保护
    2. 指数退避重试
    3. 限流控制
    4. 悬挂订单清理
    """
    
    def __init__(self, config: Optional[NetworkConfig] = None):
        self.config = config or NetworkConfig()
        self._rate_limit_window: Dict[str, list] = {}  # rate_limit -> [timestamps]
        self._pending_orders: Dict[str, dict] = {}  # order_id -> order_info
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """启动处理器"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("✅ 网络异常处理器已启动")
    
    async def stop(self):
        """停止处理器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("✅ 网络异常处理器已停止")
    
    async def execute_with_retry(self,
                                 func: Callable,
                                 *args,
                                 retry_config: Optional[RetryConfig] = None,
                                 **kwargs) -> Any:
        """
        执行带重试的函数
        
        Args:
            func: 要执行的异步函数
            retry_config: 重试配置
            
        Returns:
            函数返回值
            
        Raises:
            NetworkException: 所有重试用尽后抛出
        """
        config = retry_config or RetryConfig()
        last_exception = None
        
        for attempt in range(config.max_attempts):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.config.default_timeout_seconds
                )
            
            except asyncio.TimeoutError:
                last_exception = NetworkException(
                    NetworkErrorType.TIMEOUT,
                    f"请求超时 (第{attempt + 1}次尝试)",
                    retry_after=self._calculate_backoff(attempt, config)
                )
                logger.warning(f"⏰ {last_exception.message}")
                
            except (ConnectionError, OSError) as e:
                last_exception = NetworkException(
                    NetworkErrorType.CONNECTION,
                    f"连接错误: {e}",
                    retry_after=self._calculate_backoff(attempt, config)
                )
                logger.warning(f"🔌 {last_exception.message}")
            
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    last_exception = NetworkException(
                        NetworkErrorType.RATE_LIMIT,
                        f"限流: {e}",
                        retry_after=self.config.max_delay_seconds
                    )
                    logger.warning(f"🚫 {last_exception.message}")
                else:
                    last_exception = NetworkException(
                        NetworkErrorType.SERVER_ERROR,
                        f"服务器错误: {e}",
                        retry_after=self._calculate_backoff(attempt, config)
                    )
                    logger.error(f"❌ {last_exception.message}")
            
            # 检查是否可重试
            if not self._should_retry(attempt, config, last_exception):
                break
            
            # 等待后重试
            delay = self._calculate_backoff(attempt, config)
            if last_exception and last_exception.retry_after:
                delay = max(delay, last_exception.retry_after)
            
            await asyncio.sleep(delay)
        
        raise last_exception or NetworkException(
            NetworkErrorType.UNKNOWN,
            "未知错误"
        )
    
    def _should_retry(self, 
                      attempt: int, 
                      config: RetryConfig, 
                      exception: Exception) -> bool:
        """判断是否应该重试"""
        if attempt >= config.max_attempts - 1:
            return False
        
        if isinstance(exception, NetworkException):
            if exception.error_type == NetworkErrorType.RATE_LIMIT:
                return False  # 限流需要等待更长
        
        return True
    
    def _calculate_backoff(self, attempt: int, config: RetryConfig) -> float:
        """计算退避时间"""
        delay = config.delay * (config.exponential_base ** attempt)
        delay = min(delay, config.max_delay)
        
        if config.jitter:
            # 添加随机抖动
            jitter_range = delay * 0.1
            delay += random.uniform(-jitter_range, jitter_range)
        
        return delay
    
    def check_rate_limit(self, rate_limit_key: str = "default") -> bool:
        """
        检查是否超过限流
        
        Returns:
            True: 未超限，可以请求
            False: 已超限，需要等待
        """
        now = datetime.now().timestamp()
        window_start = now - 60  # 1分钟窗口
        
        # 获取当前窗口的请求记录
        if rate_limit_key not in self._rate_limit_window:
            self._rate_limit_window[rate_limit_key] = []
        
        timestamps = self._rate_limit_window[rate_limit_key]
        
        # 清理过期记录
        timestamps[:] = [t for t in timestamps if t > window_start]
        
        # 检查是否超限
        if len(timestamps) >= self.config.requests_per_minute:
            # 检查是否 burst
            recent_count = sum(1 for t in timestamps if t > now - 10)
            if recent_count >= self.config.burst_limit:
                logger.warning(f"🚫 触发burst限流: {rate_limit_key}")
                return False
            
            logger.warning(f"🚫 触发请求限流: {rate_limit_key}")
            return False
        
        # 记录请求
        timestamps.append(now)
        return True
    
    async def register_pending_order(self, 
                                     client_order_id: str,
                                     order_info: dict,
                                     timeout_seconds: Optional[float] = None):
        """注册悬挂订单"""
        self._pending_orders[client_order_id] = {
            "info": order_info,
            "registered_at": datetime.now(),
            "timeout_seconds": timeout_seconds or self.config.order_timeout_seconds
        }
        logger.info(f"📝 订单已注册: {client_order_id}")
    
    async def check_pending_orders(self) -> list[dict]:
        """
        检查悬挂订单
        
        Returns:
            超时需要取消的订单列表
        """
        now = datetime.now()
        timeout_orders = []
        
        for order_id, order_data in list(self._pending_orders.items()):
            registered_at = order_data["registered_at"]
            timeout_seconds = order_data["timeout_seconds"]
            
            if (now - registered_at).total_seconds() > timeout_seconds:
                timeout_orders.append({
                    "order_id": order_id,
                    "reason": "timeout",
                    "order_info": order_data["info"]
                })
                del self._pending_orders[order_id]
                logger.warning(f"⚠️ 订单超时: {order_id}")
        
        return timeout_orders
    
    async def cancel_hanging_orders(self, 
                                    orders: list,
                                    cancel_func: Callable) -> dict:
        """
        取消悬挂订单
        
        Args:
            orders: 超时订单列表
            cancel_func: 取消订单的函数
            
        Returns:
            取消结果统计
        """
        results = {"success": 0, "failed": 0, "not_found": 0}
        
        for order in orders:
            try:
                await cancel_func(order["order_info"])
                results["success"] += 1
                logger.info(f"✅ 已取消悬挂订单: {order['order_id']}")
            except Exception as e:
                if "not found" in str(e).lower():
                    results["not_found"] += 1
                else:
                    results["failed"] += 1
                    logger.error(f"❌ 取消订单失败: {order['order_id']} - {e}")
        
        return results
    
    async def _cleanup_loop(self):
        """定期清理循环"""
        while True:
            try:
                await asyncio.sleep(self.config.hanging_order_cleanup_interval_seconds)
                
                timeout_orders = await self.check_pending_orders()
                
                if timeout_orders:
                    logger.warning(f"⚠️ 发现 {len(timeout_orders)} 个悬挂订单待处理")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 清理循环错误: {e}")
    
    def get_status(self) -> dict:
        """获取状态"""
        return {
            "pending_orders": len(self._pending_orders),
            "rate_limit_keys": len(self._rate_limit_window),
            "config": {
                "default_timeout": self.config.default_timeout_seconds,
                "max_retries": self.config.max_retries,
                "requests_per_minute": self.config.requests_per_minute
            }
        }


class OrderTimeoutHandler:
    """
    订单超时处理器
    
    功能:
    1. 监控订单执行时间
    2. 超时自动撤单
    3. 状态追踪
    """
    
    def __init__(self):
        self._order_status: Dict[str, dict] = {}
        self._timeout_callbacks: list = []
    
    def register_timeout_callback(self, callback: Callable):
        """注册超时回调"""
        self._timeout_callbacks.append(callback)
    
    async def on_order_submitted(self, client_order_id: str, order_info: dict):
        """订单提交时调用"""
        self._order_status[client_order_id] = {
            "info": order_info,
            "submitted_at": datetime.now(),
            "status": "pending"
        }
    
    async def on_order_filled(self, client_order_id: str):
        """订单成交时调用"""
        if client_order_id in self._order_status:
            self._order_status[client_order_id]["status"] = "filled"
            self._order_status[client_order_id]["filled_at"] = datetime.now()
    
    async def on_order_cancelled(self, client_order_id: str, reason: str = "manual"):
        """订单取消时调用"""
        if client_order_id in self._order_status:
            self._order_status[client_order_id]["status"] = "cancelled"
            self._order_status[client_order_id]["cancelled_at"] = datetime.now()
            self._order_status[client_order_id]["cancel_reason"] = reason
    
    def get_order_status(self, client_order_id: str) -> Optional[dict]:
        """获取订单状态"""
        return self._order_status.get(client_order_id)
    
    def check_timeouts(self, 
                      timeout_seconds: float = 60.0) -> list[str]:
        """
        检查超时订单
        
        Returns:
            超时订单ID列表
        """
        now = datetime.now()
        timeout_orders = []
        
        for order_id, status in self._order_status.items():
            if status["status"] == "pending":
                elapsed = (now - status["submitted_at"]).total_seconds()
                if elapsed > timeout_seconds:
                    timeout_orders.append(order_id)
        
        return timeout_orders
    
    async def handle_timeouts(self, 
                             timeout_seconds: float,
                             cancel_func: Callable):
        """
        处理超时订单
        """
        timeout_order_ids = self.check_timeouts(timeout_seconds)
        
        for order_id in timeout_order_ids:
            # 触发回调
            for callback in self._timeout_callbacks:
                try:
                    await callback(order_id, self._order_status[order_id])
                except Exception as e:
                    logger.error(f"超时回调失败: {e}")
            
            # 取消订单
            try:
                await cancel_func(self._order_status[order_id]["info"])
                await self.on_order_cancelled(order_id, "timeout")
                logger.warning(f"⏰ 已取消超时订单: {order_id}")
            except Exception as e:
                logger.error(f"取消超时订单失败: {order_id} - {e}")


# 单例
_network_handler: Optional[NetworkHandler] = None
_timeout_handler: Optional[OrderTimeoutHandler] = None


def get_network_handler() -> NetworkHandler:
    """获取网络处理器单例"""
    global _network_handler
    if _network_handler is None:
        _network_handler = NetworkHandler()
    return _network_handler


def get_timeout_handler() -> OrderTimeoutHandler:
    """获取超时处理器单例"""
    global _timeout_handler
    if _timeout_handler is None:
        _timeout_handler = OrderTimeoutHandler()
    return _timeout_handler
