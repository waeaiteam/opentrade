"""
OpenTrade 数据库连接
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool

from opentrade.core.config import get_config


class Base(DeclarativeBase):
    """数据库基类"""
    pass


class Database:
    """数据库管理器"""
    
    _instance: "Database" = None
    _engine: AsyncEngine = None
    _session_factory: async_sessionmaker[AsyncSession] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._engine is None:
            self._init_engine()
    
    def _init_engine(self):
        """初始化引擎"""
        config = get_config()
        database_url = config.storage.database_url
        
        # 异步引擎
        self._engine = create_async_engine(
            database_url,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            echo=False,
        )
        
        # 会话工厂
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    @property
    def engine(self) -> AsyncEngine:
        return self._engine
    
    async def create_tables(self):
        """创建所有表"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def drop_tables(self):
        """删除所有表"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取数据库会话"""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self):
        """关闭连接"""
        if self._engine:
            await self._engine.dispose()


# 全局数据库实例
db = Database()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """依赖注入 - 获取数据库会话"""
    async with db.session() as session:
        yield session


# 初始化数据库
async def init_db():
    """初始化数据库"""
    await db.create_tables()
