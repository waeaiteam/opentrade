"""
OpenTrade Database - PostgreSQL + TimescaleDB

支持:
- PostgreSQL 主库
- TimescaleDB 时序扩展
- 连接池管理
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session

from opentrade.core.config import get_config


# 同步引擎
_sync_engine = None
_sync_session_factory = None

# 异步引擎
_async_engine = None
_async_session_factory = None


def get_engine(force_new: bool = False):
    """获取同步数据库引擎"""
    global _sync_engine, _sync_session_factory

    if _sync_engine is None or force_new:
        config = get_config()
        _sync_engine = create_engine(
            config.storage.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        _sync_session_factory = sessionmaker(bind=_sync_engine)

    return _sync_engine


def get_session() -> Session:
    """获取同步会话"""
    factory = _sync_session_factory
    if factory is None:
        get_engine()
        factory = _sync_session_factory
    return factory()


def get_async_engine():
    """获取异步数据库引擎"""
    global _async_engine, _async_session_factory

    if _async_engine is None:
        config = get_config()
        # 转换 postgresql:// → postgresql+asyncpg://
        db_url = config.storage.database_url
        if "postgresql://" in db_url:
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        elif "postgres://" in db_url:
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://")

        _async_engine = create_async_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        _async_session_factory = async_sessionmaker(
            _async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _async_engine


def get_async_session() -> AsyncSession:
    """获取异步会话"""
    factory = _async_session_factory
    if factory is None:
        get_async_engine()
        factory = _async_session_factory
    return factory()


@asynccontextmanager
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """异步会话上下文"""
    session = get_async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def init_database():
    """初始化数据库表结构"""
    engine = get_engine()

    # 创建表结构
    from opentrade.models.base import Base

    Base.metadata.create_all(engine)

    print(f"[Database] ✅ 表结构初始化完成")


async def init_async_database():
    """异步初始化数据库"""
    engine = get_async_engine()

    from opentrade.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("[Database] ✅ 异步表结构初始化完成")


def check_connection() -> bool:
    """检查数据库连接"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[Database] ❌ 连接失败: {e}")
        return False


async def check_async_connection() -> bool:
    """异步检查数据库连接"""
    try:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"[Database] ❌ 异步连接失败: {e}")
        return False
