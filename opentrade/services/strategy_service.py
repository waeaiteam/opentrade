"""
OpenTrade 策略服务
"""

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from opentrade.core.config import get_config
from opentrade.core.database import db
from opentrade.models.strategy import (
    Strategy,
    StrategyEvolution,
    StrategyStatus,
    StrategyType,
    StrategyVersion,
)


class StrategyService:
    """策略服务
    
    负责策略的创建、加载、保存、
    版本管理和进化逻辑。
    """

    def __init__(self):
        self.config = get_config()
        self._strategy_dir = Path.home() / ".opentrade" / "strategies"
        self._strategy_dir.mkdir(parents=True, exist_ok=True)

    async def create_strategy(
        self,
        name: str,
        strategy_type: str,
        parameters: dict,
        description: str = "",
    ) -> Strategy:
        """创建新策略"""
        strategy = Strategy(
            id=uuid4(),
            name=name,
            version="1.0.0",
            description=description,
            strategy_type=StrategyType(strategy_type),
            status=StrategyStatus.TESTING,
            parameters=json.dumps(parameters),
        )

        async with db.session() as session:
            session.add(strategy)

        return strategy

    async def load_strategy(self, strategy_id: str) -> Strategy | None:
        """加载策略"""
        async with db.session() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            return result.scalar_one_or_none()

    async def list_strategies(
        self,
        status: StrategyStatus = None,
        strategy_type: StrategyType = None,
    ) -> list[Strategy]:
        """列出策略"""
        async with db.session() as session:
            query = select(Strategy)

            if status:
                query = query.where(Strategy.status == status)
            if strategy_type:
                query = query.where(Strategy.strategy_type == strategy_type)

            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_strategy(
        self,
        strategy_id: str,
        parameters: dict = None,
        performance: dict = None,
    ) -> Strategy | None:
        """更新策略"""
        async with db.session() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy:
                return None

            if parameters:
                strategy.parameters = json.dumps(parameters)

            if performance:
                if "win_rate" in performance:
                    strategy.win_rate = performance["win_rate"]
                if "profit_factor" in performance:
                    strategy.profit_factor = performance["profit_factor"]
                if "sharpe_ratio" in performance:
                    strategy.sharpe_ratio = performance["sharpe_ratio"]
                if "max_drawdown" in performance:
                    strategy.max_drawdown = performance["max_drawdown"]
                if "total_trades" in performance:
                    strategy.total_trades = performance["total_trades"]
                if "total_pnl" in performance:
                    strategy.total_pnl = performance["total_pnl"]

            strategy.updated_at = __import__("datetime").datetime.utcnow()

            return strategy

    async def evolve_strategy(
        self,
        strategy_id: str,
        evolution_type: str,
        changes: dict,
    ) -> tuple[Strategy, StrategyEvolution]:
        """进化策略"""
        async with db.session() as session:
            # 获取原策略
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            original = result.scalar_one_or_none()

            if not original:
                raise ValueError("策略不存在")

            # 保存版本历史
            version = StrategyVersion(
                id=uuid4(),
                strategy_id=strategy_id,
                version=original.version,
                parameters=original.parameters,
                performance=json.dumps({
                    "win_rate": original.win_rate,
                    "profit_factor": original.profit_factor,
                    "sharpe_ratio": original.sharpe_ratio,
                    "max_drawdown": original.max_drawdown,
                    "total_trades": original.total_trades,
                    "total_pnl": original.total_pnl,
                }),
                created_at=__import__("datetime").datetime.utcnow(),
            )
            session.add(version)

            # 创建新版本
            new_params = json.loads(original.parameters)
            new_params.update(changes)

            # 更新版本号
            version_parts = original.version.split(".")
            version_parts[-1] = str(int(version_parts[-1]) + 1)
            new_version = ".".join(version_parts)

            # 创建进化记录
            evolution = StrategyEvolution(
                id=uuid4(),
                strategy_id=strategy_id,
                generation=1,
                evolution_type=evolution_type,
                changes=json.dumps(changes),
                before_performance=json.dumps({
                    "win_rate": original.win_rate,
                    "profit_factor": original.profit_factor,
                }),
                created_at=__import__("datetime").datetime.utcnow(),
            )
            session.add(evolution)

            # 更新原策略
            original.parameters = json.dumps(new_params)
            original.version = new_version
            original.parent_id = strategy_id

            return original, evolution

    async def archive_strategy(self, strategy_id: str):
        """归档策略"""
        async with db.session() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if strategy:
                strategy.status = StrategyStatus.ARCHIVED

    async def export_strategy(self, strategy_id: str) -> dict:
        """导出策略"""
        async with db.session() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy:
                raise ValueError("策略不存在")

            return {
                "id": str(strategy.id),
                "name": strategy.name,
                "version": strategy.version,
                "description": strategy.description,
                "type": strategy.strategy_type.value,
                "parameters": json.loads(strategy.parameters),
                "performance": {
                    "win_rate": strategy.win_rate,
                    "profit_factor": strategy.profit_factor,
                    "sharpe_ratio": strategy.sharpe_ratio,
                    "max_drawdown": strategy.max_drawdown,
                    "total_trades": strategy.total_trades,
                    "total_pnl": strategy.total_pnl,
                },
            }

    async def import_strategy(self, data: dict) -> Strategy:
        """导入策略"""
        return await self.create_strategy(
            name=data["name"],
            strategy_type=data["type"],
            parameters=data.get("parameters", {}),
            description=data.get("description", ""),
        )

    # 预定义策略
    async def get_builtin_strategies(self) -> list[dict]:
        """获取内置策略"""
        return [
            {
                "id": "trend_following",
                "name": "趋势跟踪",
                "type": StrategyType.TREND_FOLLOWING,
                "description": "基于趋势的技术分析策略",
                "parameters": {
                    "ema_fast": 9,
                    "ema_slow": 21,
                    "rsi_period": 14,
                    "stop_loss": 0.05,
                    "take_profit": 0.10,
                },
            },
            {
                "id": "mean_reversion",
                "name": "均值回归",
                "type": StrategyType.MEAN_REVERSION,
                "description": "基于价格回归均值的策略",
                "parameters": {
                    "bb_period": 20,
                    "bb_std": 2,
                    "rsi_overbought": 70,
                    "rsi_oversold": 30,
                    "stop_loss": 0.03,
                    "take_profit": 0.06,
                },
            },
            {
                "id": "grid_trading",
                "name": "网格交易",
                "type": StrategyType.GRID_TRADING,
                "description": "在价格区间内自动网格交易",
                "parameters": {
                    "grid_levels": 10,
                    "grid_spacing": 0.02,
                    "stop_loss": 0.10,
                    "take_profit": 0.15,
                },
            },
            {
                "id": "scalping",
                "name": "高频套利",
                "type": StrategyType.SCALPING,
                "description": "短周期快速交易策略",
                "parameters": {
                    "ema_fast": 5,
                    "ema_slow": 13,
                    "rsi_period": 7,
                    "stop_loss": 0.01,
                    "take_profit": 0.02,
                    "trailing_stop": 0.01,
                },
            },
        ]
