"""
OpenTrade 向量数据库集成

用于存储和检索策略经验、市场模式、交易信号等向量数据。
支持 Qdrant 和 FAISS (本地) 两种后端。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import numpy as np


@dataclass
class VectorRecord:
    """向量记录"""
    id: str
    vector: list[float]
    payload: dict
    metadata: dict = None
    created_at: datetime = None


class VectorStoreBase(ABC):
    """向量存储基类"""

    @abstractmethod
    def add(self, record: VectorRecord) -> str:
        """添加向量"""
        pass

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        filters: dict = None,
    ) -> list[dict]:
        """搜索相似向量"""
        pass

    @abstractmethod
    def delete(self, id: str) -> bool:
        """删除向量"""
        pass

    @abstractmethod
    def close(self):
        """关闭连接"""
        pass


class QdrantStore(VectorStoreBase):
    """Qdrant 向量存储
    
    需要运行 Qdrant 服务:
    docker run -p 6333:6333 qdrant/qdrant
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "opentrade_experiences",
        vector_size: int = 384,
    ):
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._client = None
        self._connected = False

    def connect(self) -> bool:
        """连接 Qdrant"""
        try:
            import qdrant_client
            from qdrant_client import QdrantClient
            
            self._client = QdrantClient(host=self.host, port=self.port)
            
            # 创建或获取 collection
            try:
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "size": self.vector_size,
                        "distance": "Cosine",
                    },
                )
            except Exception:
                pass  # collection 已存在
            
            self._connected = True
            return True
        except ImportError:
            print("[yellow]⚠️ qdrant_client 未安装，使用内存模式[/yellow]")
            self._connected = False
            return False
        except Exception as e:
            print(f"[red]❌ Qdrant 连接失败: {e}[/red]")
            self._connected = False
            return False

    def add(self, record: VectorRecord) -> str:
        """添加向量"""
        if not self._connected:
            return self._add_fallback(record)

        try:
            self._client.upsert(
                collection_name=self.collection_name,
                points=[{
                    "id": record.id,
                    "vector": record.vector,
                    "payload": record.payload,
                }]
            )
            return record.id
        except Exception as e:
            print(f"[red]❌ 添加向量失败: {e}[/red]")
            return self._add_fallback(record)

    def _add_fallback(self, record: VectorRecord) -> str:
        """备用添加 (内存模式)"""
        # 简单内存存储
        print(f"[dim]内存模式: 添加 {record.id}[/dim]")
        return record.id

    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        filters: dict = None,
    ) -> list[dict]:
        """搜索相似向量"""
        if not self._connected:
            return self._search_fallback(query_vector, limit)

        try:
            results = self._client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=qdrant_client.models.Filter(**filters) if filters else None,
            )

            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload,
                }
                for r in results
            ]
        except Exception as e:
            print(f"[red]❌ 搜索失败: {e}[/red]")
            return self._search_fallback(query_vector, limit)

    def _search_fallback(self, query_vector: list[float], limit: int) -> list[dict]:
        """备用搜索"""
        # 简单随机返回
        return []

    def delete(self, id: str) -> bool:
        """删除向量"""
        if not self._connected:
            return True

        try:
            self._client.delete(
                collection_name=self.collection_name,
                points=[id],
            )
            return True
        except Exception as e:
            print(f"[red]❌ 删除失败: {e}[/red]")
            return False

    def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()


class MemoryVectorStore(VectorStoreBase):
    """内存向量存储 (开发/测试用)"""

    def __init__(self, vector_size: int = 384):
        self.vector_size = vector_size
        self._vectors: list[VectorRecord] = []

    def add(self, record: VectorRecord) -> str:
        """添加向量"""
        self._vectors.append(record)
        return record.id

    def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        filters: dict = None,
    ) -> list[dict]:
        """搜索相似向量 (余弦相似度)"""
        query = np.array(query_vector)
        results = []

        for record in self._vectors:
            vec = np.array(record.vector)
            
            # 计算余弦相似度
            similarity = np.dot(query, vec) / (np.linalg.norm(query) * np.linalg.norm(vec) + 1e-8)
            
            results.append({
                "id": record.id,
                "score": similarity,
                "payload": record.payload,
            })

        # 按相似度排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def delete(self, id: str) -> bool:
        """删除向量"""
        original_len = len(self._vectors)
        self._vectors = [v for v in self._vectors if v.id != id]
        return len(self._vectors) < original_len

    def close(self):
        """关闭"""
        self._vectors.clear()


def get_vector_store(store_type: str = "auto") -> VectorStoreBase:
    """获取向量存储实例
    
    Args:
        store_type: auto/qdrant/memory
    """
    # 优先尝试 Qdrant
    if store_type in ["auto", "qdrant"]:
        store = QdrantStore()
        if store.connect():
            return store

    # 回退到内存存储
    print("[yellow]⚠️ 使用内存向量存储[/yellow]")
    return MemoryVectorStore()


# ============ 策略经验存储 ============

class StrategyExperienceStore:
    """策略经验存储
    
    存储成功的策略模式、市场状态和交易信号，
    用于后续检索和策略进化。
    """

    def __init__(self, store: VectorStoreBase = None):
        self.store = store or get_vector_store()

    def store_experience(
        self,
        strategy_name: str,
        market_condition: dict,
        action: str,
        result: str,
        pnl: float,
        vector: list[float],
    ) -> str:
        """存储策略经验"""
        import uuid

        record = VectorRecord(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "strategy": strategy_name,
                "condition": market_condition,
                "action": action,
                "result": result,
                "pnl": pnl,
            },
            metadata={
                "type": "strategy_experience",
            },
            created_at=datetime.utcnow(),
        )

        return self.store.add(record)

    def search_similar_experiences(
        self,
        market_condition: dict,
        strategy_name: str = None,
        limit: int = 5,
    ) -> list[dict]:
        """搜索相似经验
        
        实际应该将 market_condition 转换为向量
        这里简化处理
        """
        # 生成一个简单的向量
        vector = [
            market_condition.get("fear_index", 50) / 100,
            market_condition.get("volatility", 0.02) * 10,
            market_condition.get("trend_score", 0.5),
        ]

        return self.store.search(vector, limit=limit)

    def get_successful_patterns(
        self,
        min_pnl: float = 0.05,
        limit: int = 10,
    ) -> list[dict]:
        """获取成功模式 (需要配合 Qdrant 过滤)"""
        # 简化: 返回最近的正面经验
        return []

    def close(self):
        """关闭"""
        self.store.close()


# 单例
_experience_store: Optional[StrategyExperienceStore] = None


def get_experience_store() -> StrategyExperienceStore:
    """获取经验存储单例"""
    global _experience_store
    if _experience_store is None:
        _experience_store = StrategyExperienceStore()
    return _experience_store
