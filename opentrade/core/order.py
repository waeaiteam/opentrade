"""
订单幂等性模块
确保每笔订单唯一，防止重复下单
"""
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderIdempotencyConfig:
    """幂等性配置"""
    id_length: int = 32           # ID长度
    cache_ttl_hours: int = 24    # 缓存过期时间
    dedup_window_ms: int = 5000  # 去重窗口 (毫秒)


class OrderIdempotencyManager:
    """
    订单幂等性管理器
    
    功能:
    1. 生成唯一 clientOrderId
    2. 检测重复订单
    3. 防止网络波动导致的重复下单
    """
    
    def __init__(self, config: Optional[OrderIdempotencyConfig] = None):
        self.config = config or OrderIdempotencyConfig()
        self._order_cache: Dict[str, datetime] = {}
        self._cache_file = Path("/root/.opentrade/data/order_idempotency.json")
        self._load_cache()
    
    def _load_cache(self):
        """加载缓存"""
        if self._cache_file.exists():
            try:
                data = json.loads(self._cache_file.read_text())
                self._order_cache = {
                    k: datetime.fromisoformat(v) 
                    for k, v in data.items()
                }
                logger.info(f"✅ 幂等性缓存已加载: {len(self._order_cache)} 条记录")
            except Exception as e:
                logger.warning(f"⚠️ 幂等性缓存加载失败: {e}")
    
    def _save_cache(self):
        """保存缓存"""
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            k: v.isoformat() 
            for k, v in self._order_cache.items()
        }
        self._cache_file.write_text(json.dumps(data))
    
    def generate_client_order_id(self, 
                                 action: str,
                                 symbol: str,
                                 price: float,
                                 size: float,
                                 timestamp: Optional[int] = None) -> str:
        """
        生成唯一的 clientOrderId
        
        格式: {action}_{symbol}_{timestamp}_{random}
        示例: BUY_BTCUSDT_1708300000000_a1b2c3d4
        """
        ts = timestamp or int(datetime.now().timestamp() * 1000)
        random_suffix = uuid.uuid4().hex[:8]
        
        # 清理symbol中的非法字符
        clean_symbol = symbol.replace("/", "").replace("-", "").upper()
        
        client_order_id = f"{action}_{clean_symbol}_{ts}_{random_suffix}"
        
        return client_order_id
    
    def generate_idempotency_key(self, 
                                 action: str,
                                 symbol: str,
                                 price: float,
                                 size: float,
                                 timestamp: Optional[int] = None) -> str:
        """
        生成幂等性Key (用于检测重复订单)
        
        基于订单核心参数生成唯一标识
        """
        ts = timestamp or int(datetime.now().timestamp() * 1000)
        
        # 核心参数组合
        core_params = f"{action}:{symbol}:{price}:{size}:{ts}"
        
        # SHA256 哈希
        key = hashlib.sha256(core_params.encode()).hexdigest()[:self.config.id_length]
        
        return f"order_{key}"
    
    def is_duplicate(self, idempotency_key: str) -> bool:
        """
        检查是否重复订单
        
        Returns:
            True: 重复订单，已存在
            False: 新订单
        """
        now = datetime.now()
        
        # 清理过期记录
        expired_keys = [
            k for k, t in self._order_cache.items()
            if (now - t).total_seconds() > self.config.cache_ttl_hours * 3600
        ]
        for k in expired_keys:
            del self._order_cache[k]
        
        # 检查是否重复
        if idempotency_key in self._order_cache:
            logger.warning(f"⚠️ 检测到重复订单: {idempotency_key}")
            return True
        
        return False
    
    def mark_order_processed(self, 
                             client_order_id: str,
                             idempotency_key: str,
                             status: str = "submitted"):
        """
        标记订单已处理
        
        Args:
            client_order_id: 客户端订单ID
            idempotency_key: 幂等性Key
            status: 订单状态
        """
        self._order_cache[idempotency_key] = datetime.now()
        self._save_cache()
        
        logger.info(f"✅ 订单已记录: {client_order_id} [{status}]")
    
    def check_and_process(self, 
                          action: str,
                          symbol: str,
                          price: float,
                          size: float) -> tuple[bool, Optional[str], str]:
        """
        检查并处理订单幂等性
        
        Returns:
            (是否允许执行, clientOrderId, 消息)
        """
        idempotency_key = self.generate_idempotency_key(action, symbol, price, size)
        
        if self.is_duplicate(idempotency_key):
            return False, "", "重复订单已被拒绝"
        
        client_order_id = self.generate_client_order_id(action, symbol, price, size)
        
        return True, client_order_id, "订单允许执行"
    
    def validate_client_order_id(self, client_order_id: str) -> bool:
        """
        验证 clientOrderId 格式
        
        格式: {action}_{symbol}_{timestamp}_{random}
        """
        try:
            parts = client_order_id.split("_")
            if len(parts) != 4:
                return False
            
            # 验证action
            valid_actions = {"BUY", "SELL", "CLOSE", "FLAT"}
            if parts[0] not in valid_actions:
                return False
            
            # 验证时间戳
            if not parts[2].isdigit():
                return False
            
            return True
        except Exception:
            return False
    
    def cancel_order(self, client_order_id: str):
        """
        取消订单时清理幂等性缓存
        
        如果订单被取消，释放幂等性Key，允许重新下单
        """
        # 这里可以根据业务逻辑决定是否清理
        # 通常不建议清理，避免取消后立即重下
        pass
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        now = datetime.now()
        valid_count = sum(
            1 for t in self._order_cache.values()
            if (now - t).total_seconds() <= self.config.cache_ttl_hours * 3600
        )
        
        return {
            "total_cached_orders": len(self._order_cache),
            "valid_orders": valid_count,
            "cache_ttl_hours": self.config.cache_ttl_hours
        }


class OrderDeduplicator:
    """
    订单去重器 - 基于时间窗口的去重
    """
    
    def __init__(self, window_ms: int = 5000):
        self.window_ms = window_ms
        self._recent_orders: Dict[str, int] = {}  # order_hash -> timestamp
    
    def is_duplicate_in_window(self, 
                               action: str,
                               symbol: str,
                               price: float,
                               size: float) -> bool:
        """
        检查时间窗口内的重复订单
        
        Returns:
            True: 重复
            False: 新订单
        """
        order_hash = self._get_order_hash(action, symbol, price, size)
        current_time = datetime.now().timestamp() * 1000
        
        if order_hash in self._recent_orders:
            last_time = self._recent_orders[order_hash]
            if current_time - last_time < self.window_ms:
                logger.warning(f"⚠️ 窗口内重复订单检测: {order_hash}")
                return True
        
        # 更新记录
        self._recent_orders[order_hash] = current_time
        
        # 清理过期记录
        self._cleanup_expired(current_time)
        
        return False
    
    def _get_order_hash(self, 
                       action: str,
                       symbol: str,
                       price: float,
                       size: float) -> str:
        """生成订单哈希"""
        return hashlib.md5(
            f"{action}:{symbol}:{price}:{size}".encode()
        ).hexdigest()
    
    def _cleanup_expired(self, current_time: float):
        """清理过期记录"""
        cutoff = current_time - self.window_ms * 2
        expired = [
            k for k, t in self._recent_orders.items()
            if t < cutoff
        ]
        for k in expired:
            del self._recent_orders[k]


# 单例
_idempotency_manager: Optional[OrderIdempotencyManager] = None


def get_idempotency_manager() -> OrderIdempotencyManager:
    """获取幂等性管理器单例"""
    global _idempotency_manager
    if _idempotency_manager is None:
        _idempotency_manager = OrderIdempotencyManager()
    return _idempotency_manager
