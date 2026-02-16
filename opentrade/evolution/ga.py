from __future__ import annotations

"""
OpenTrade 策略进化引擎 - GA + RL

实现:
1. 遗传算法 (GA) - 参数优化、策略进化
2. 强化学习 (RL) - 离线训练、策略改进
3. 策略回放 - 验证进化效果

进化流程:
    ┌────────────────────────────────────────────────────────┐
    │                   种群初始化                            │
    │           (随机参数组合、模板变体)                        │
    └────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌─────────┐     ┌─────────┐     ┌─────────┐
        │ 个体1   │     │ 个体2   │     │ 个体N   │
        │ (策略)  │     │ (策略)  │     │ (策略)  │
        └────┬────┘     └────┬────┘     └────┬────┘

             │               │               │
             └───────────────┼───────────────┘
                             ▼
                    ┌────────────────┐
                    │   适应度评估     │
                    │ (回测收益/风险)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌─────────┐   ┌─────────┐   ┌─────────┐
        │  精英   │   │  交叉   │   │  变异   │
        │选择     │   │  重组   │   │  突变   │
        └────┬────┘   └────┬────┘   └────┬────┘
             │              │              │
             └──────────────┼──────────────┘
                             ▼
                    ┌────────────────┐
                    │  新一代生成      │
                    │  (迭代循环)     │
                    └────────────────┘
"""

import asyncio
import json
import random
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


# ============ 策略基因 ============

class GeneType(str, Enum):
    """基因类型"""
    ENTRY_CONDITION = "entry_condition"  # 入场条件
    EXIT_CONDITION = "exit_condition"    # 出场条件
    STOP_LOSS = "stop_loss"              # 止损
    TAKE_PROFIT = "take_profit"          # 止盈
    POSITION_SIZE = "position_size"      # 仓位大小
    TIMEFRAME = "timeframe"              # 时间框架
    INDICATOR_PARAM = "indicator_param"  # 指标参数


@dataclass
class Gene:
    """策略基因"""
    gene_type: GeneType
    value: Any
    mutation_range: tuple | None = None  # 变异范围
    mutation_prob: float = 0.1  # 变异概率

    def mutate(self) -> "Gene":
        """基因变异"""
        if random.random() > self.mutation_prob:
            return self

        if self.mutation_range:
            if isinstance(self.value, float):
                self.value = round(
                    random.uniform(*self.mutation_range),
                    4,
                )
            elif isinstance(self.value, int):
                self.value = random.randint(*self.mutation_range)

        return self

    def crossover(self, other: "Gene") -> tuple["Gene", "Gene"]:
        """基因交叉"""
        return (
            Gene(
                gene_type=self.gene_type,
                value=self.value,
                mutation_range=self.mutation_range,
                mutation_prob=self.mutation_prob,
            ),
            Gene(
                gene_type=other.gene_type,
                value=other.value,
                mutation_range=other.mutation_range,
                mutation_prob=other.mutation_prob,
            ),
        )

    def copy(self) -> "Gene":
        """复制基因"""
        return Gene(
            gene_type=self.gene_type,
            value=self.value,
            mutation_range=self.mutation_range,
            mutation_prob=self.mutation_prob,
        )


@dataclass
class StrategyGenome:
    """策略基因组"""
    genome_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    genes: dict[GeneType, Gene] = field(default_factory=dict)

    # 元数据
    generation: int = 0
    fitness: float = 0.0
    parent_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def add_gene(
        self,
        gene_type: GeneType,
        value: Any,
        mutation_range: tuple | None = None,
        mutation_prob: float = 0.1,
    ) -> "StrategyGenome":
        """添加基因"""
        self.genes[gene_type] = Gene(
            gene_type=gene_type,
            value=value,
            mutation_range=mutation_range,
            mutation_prob=mutation_prob,
        )
        return self

    def get(self, gene_type: GeneType, default: Any = None) -> Any:
        """获取基因值"""
        gene = self.genes.get(gene_type)
        return gene.value if gene else default

    def mutate(self) -> "StrategyGenome":
        """变异"""
        new_genome = StrategyGenome(
            generation=self.generation + 1,
            parent_id=self.genome_id,
        )
        for gene_type, gene in self.genes.items():
            new_genome.genes[gene_type] = gene.mutate()
        return new_genome

    def crossover(self, other: "StrategyGenome") -> tuple["StrategyGenome", "StrategyGenome"]:
        """交叉"""
        child1 = StrategyGenome(generation=max(self.generation, other.generation) + 1)
        child2 = StrategyGenome(generation=max(self.generation, other.generation) + 1)

        for gene_type in self.genes:
            g1, g2 = self.genes[gene_type].crossover(other.genes.get(gene_type))
            child1.genes[gene_type] = g1
            child2.genes[gene_type] = g2

        return child1, child2

    def copy(self) -> "StrategyGenome":
        """复制"""
        genome = StrategyGenome(
            genome_id=self.genome_id,
            generation=self.generation,
            fitness=self.fitness,
            parent_id=self.parent_id,
        )
        for gene_type, gene in self.genes.items():
            genome.genes[gene_type] = gene.copy()
        return genome

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "genome_id": self.genome_id,
            "genes": {
                gt.value: {
                    "value": g.value,
                    "mutation_prob": g.mutation_prob,
                }
                for gt, g in self.genes.items()
            },
            "generation": self.generation,
            "fitness": self.fitness,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyGenome":
        """从字典创建"""
        genome = cls(
            genome_id=data.get("genome_id", str(uuid.uuid4())[:8]),
            generation=data.get("generation", 0),
            fitness=data.get("fitness", 0.0),
            parent_id=data.get("parent_id"),
        )
        for gt, g in data.get("genes", {}).items():
            gene_type = GeneType(gt)
            genome.genes[gene_type] = Gene(
                gene_type=gene_type,
                value=g["value"],
                mutation_prob=g.get("mutation_prob", 0.1),
            )
        return genome


# ============ 适应度评估 ============

@dataclass
class FitnessResult:
    """适应度评估结果"""
    genome_id: str
    total_return: float = 0.0  # 总收益
    sharpe_ratio: float = 0.0  # 夏普比率
    max_drawdown: float = 0.0  # 最大回撤
    win_rate: float = 0.0     # 胜率
    profit_factor: float = 0.0 # 盈利因子
    trade_count: int = 0      # 交易次数
    fitness: float = 0.0       # 综合适应度

    def to_dict(self) -> dict:
        return {
            "genome_id": self.genome_id,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "trade_count": self.trade_count,
            "fitness": self.fitness,
        }


class FitnessEvaluator:
    """适应度评估器"""

    def __init__(
        self,
        return_weight: float = 0.3,
        sharpe_weight: float = 0.3,
        drawdown_weight: float = 0.2,
        winrate_weight: float = 0.2,
    ):
        self.weights = {
            "return": return_weight,
            "sharpe": sharpe_weight,
            "drawdown": drawdown_weight,
            "winrate": winrate_weight,
        }

    def evaluate(self, trades: list[dict], genome_id: str) -> FitnessResult:
        """评估适应度"""
        if not trades:
            return FitnessResult(genome_id=genome_id, fitness=0.0)

        # 计算各项指标
        returns = [t.get("pnl_pct", 0) for t in trades]

        total_return = sum(returns) * 100
        win_trades = [r for r in returns if r > 0]
        loss_trades = [r for r in returns if r <= 0]

        win_rate = len(win_trades) / len(returns) if returns else 0
        trade_count = len(returns)

        # 计算夏普比率 (简化)
        if len(returns) > 1:
            import statistics
            mean_ret = statistics.mean(returns)
            std_ret = statistics.stdev(returns) if len(returns) > 1 else 0.001
            sharpe_ratio = mean_ret / std_ret * 100 if std_ret > 0 else 0
        else:
            sharpe_ratio = 0

        # 最大回撤
        cumulative = [0]
        for r in returns:
            cumulative.append(cumulative[-1] * (1 + r / 100))
        peak = max(cumulative)
        drawdown = min((c - peak) / peak for c in cumulative)
        max_drawdown = abs(drawdown * 100) if drawdown < 0 else 0

        # 盈利因子
        profit_sum = sum(win_trades) if win_trades else 0
        loss_sum = abs(sum(loss_trades)) if loss_trades else 0.001
        profit_factor = profit_sum / loss_sum

        # 综合适应度
        # 夏普和回撤越大越好，需要反转
        fitness = (
            self.weights["return"] * max(total_return, 0) +
            self.weights["sharpe"] * max(sharpe_ratio, 0) +
            self.weights["drawdown"] * (20 - min(max_drawdown, 20)) +  # 回撤越小越好
            self.weights["winrate"] * win_rate * 100
        )

        # 惩罚交易次数过少
        if trade_count < 10:
            fitness *= 0.5

        return FitnessResult(
            genome_id=genome_id,
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            trade_count=trade_count,
            fitness=fitness,
        )


# ============ 遗传算法核心 ============

class GeneticAlgorithm:
    """遗传算法引擎"""

    def __init__(
        self,
        population_size: int = 50,
        elite_size: int = 5,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.1,
        generations: int = 20,
        evaluator: FitnessEvaluator | None = None,
    ):
        self.population_size = population_size
        self.elite_size = elite_size
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.generations = generations
        self.evaluator = evaluator or FitnessEvaluator()

        # 种群
        self.population: list[StrategyGenome] = []
        self.generation = 0
        self.best_genome: StrategyGenome | None = None

        # 历史
        self.history: list[dict] = []

    def initialize_population(self, template: StrategyGenome | None = None) -> "GeneticAlgorithm":
        """初始化种群"""
        self.population = []

        for i in range(self.population_size):
            if template and i < 3:
                # 前3个使用模板变异
                genome = template.mutate()
            else:
                # 随机初始化
                genome = self._random_genome()
            genome.generation = 0
            self.population.append(genome)

        return self

    def _random_genome(self) -> StrategyGenome:
        """随机生成基因组"""
        genome = StrategyGenome()

        genome.add_gene(GeneType.ENTRY_CONDITION, random.choice(["EMA_CROSS", "RSI_OVERBOUGHT", "MACD_CROSS"]))
        genome.add_gene(GeneType.EXIT_CONDITION, random.choice(["RSI_OVERSOLD", "TRAILING_STOP", "TIME_EXIT"]))
        genome.add_gene(GeneType.STOP_LOSS, random.uniform(2.0, 10.0), (1.0, 15.0))
        genome.add_gene(GeneType.TAKE_PROFIT, random.uniform(4.0, 20.0), (3.0, 30.0))
        genome.add_gene(GeneType.POSITION_SIZE, random.uniform(0.05, 0.3), (0.01, 0.5))
        genome.add_gene(GeneType.TIMEFRAME, random.choice(["5m", "15m", "1h", "4h"]))
        genome.add_gene(GeneType.INDICATOR_PARAM, random.randint(14, 28), (5, 50))

        return genome

    def evaluate_population(self, evaluate_func: callable):
        """评估整个种群"""
        results = []

        for genome in self.population:
            trades = evaluate_func(genome)
            result = self.evaluator.evaluate(trades, genome.genome_id)
            genome.fitness = result.fitness
            results.append((genome, result))

        # 排序
        results.sort(key=lambda x: x[0].fitness, reverse=True)

        # 更新最佳
        if results:
            self.best_genome = results[0][0].copy()

        # 记录历史
        fitness_scores = [g.fitness for g in self.population]
        import statistics
        self.history.append({
            "generation": self.generation,
            "best_fitness": max(fitness_scores),
            "avg_fitness": statistics.mean(fitness_scores),
            "best_genome": self.best_genome.to_dict() if self.best_genome else None,
        })

        return results

    def evolve(self) -> "GeneticAlgorithm":
        """进化一代"""
        # 按适应度排序
        self.population.sort(key=lambda g: g.fitness, reverse=True)

        # 精英选择
        elite = self.population[:self.elite_size]

        # 生成新一代
        new_population = [g.copy() for g in elite]  # 保留精英

        while len(new_population) < self.population_size:
            # 选择父母
            parent1, parent2 = self._tournament_select(2), self._tournament_select(2)

            # 交叉
            if random.random() < self.crossover_rate:
                child1, child2 = parent1.crossover(parent2)
            else:
                child1, child2 = parent1.copy(), parent2.copy()

            # 变异
            if random.random() < self.mutation_rate:
                child1 = child1.mutate()
            if random.random() < self.mutation_rate:
                child2 = child2.mutate()

            new_population.append(child1)
            if len(new_population) < self.population_size:
                new_population.append(child2)

        self.population = new_population
        self.generation += 1

        return self

    def _tournament_select(self, tournament_size: int) -> StrategyGenome:
        """锦标赛选择"""
        tournament = random.sample(self.population, min(tournament_size, len(self.population)))
        return max(tournament, key=lambda g: g.fitness)

    async def run(
        self,
        evaluate_func: callable,
        progress_callback: callable | None = None,
    ) -> StrategyGenome:
        """运行完整进化过程"""
        # 初始化
        self.initialize_population()

        for gen in range(self.generations):
            self.generation = gen

            # 评估
            results = self.evaluate_population(evaluate_func)

            # 进度回调
            if progress_callback:
                progress_callback(
                    generation=gen,
                    best_fitness=results[0][0].fitness if results else 0,
                    best_genome=results[0][0] if results else None,
                )

            # 进化
            if gen < self.generations - 1:
                self.evolve()

        return self.best_genome

    def get_stats(self) -> dict:
        """获取进化统计"""
        return {
            "current_generation": self.generation,
            "population_size": len(self.population),
            "best_fitness": self.best_genome.fitness if self.best_genome else 0,
            "history": self.history,
        }


# ============ 策略回放器 ============

class StrategyReplay:
    """策略回放器 - 验证进化效果"""

    def __init__(self, executor):
        self.executor = executor
        self.trades: list[dict] = []

    async def replay(
        self,
        genome: StrategyGenome,
        symbol: str,
        start_time: str,
        end_time: str,
        initial_balance: float = 10000,
    ) -> list[dict]:
        """回放策略交易"""
        # 重置模拟账户
        if hasattr(self.executor, 'adapter') and self.executor.adapter.is_simulated:
            self.executor.adapter.reset(initial_balance)

        self.trades = []

        # 从基因组提取参数
        stop_loss_pct = genome.get(GeneType.STOP_LOSS, 5.0)
        take_profit_pct = genome.get(GeneType.TAKE_PROFIT, 10.0)
        position_size = genome.get(GeneType.POSITION_SIZE, 0.1)

        # 模拟交易逻辑 (简化版)
        position = None
        entry_price = 0

        # 获取价格历史
        prices = await self._get_price_history(symbol, start_time, end_time)

        for i, price_data in enumerate(prices):
            price = price_data["price"]
            timestamp = price_data["timestamp"]

            if position is None:
                # 检查入场信号 (简化: 连续3根上涨)
                if i >= 3:
                    prev_prices = [p["price"] for p in prices[i-3:i]]
                    if all(prev_prices[j] < prev_prices[j+1] for j in range(2)):
                        # 入场
                        quantity = (initial_balance * position_size) / price
                        order = await self.executor.buy(
                            symbol,
                            quantity=quantity,
                            price=price,
                            stop_loss=price * (1 - stop_loss_pct / 100),
                            take_profit=price * (1 + take_profit_pct / 100),
                            strategy_id=genome.genome_id,
                        )
                        if order.status.value == "FILLED":
                            position = {
                                "side": "LONG",
                                "entry_price": price,
                                "quantity": order.filled_quantity,
                            }

            else:
                # 检查出场
                pnl_pct = (price - position["entry_price"]) / position["entry_price"] * 100

                if pnl_pct >= take_profit_pct or pnl_pct <= -stop_loss_pct:
                    # 平仓
                    order = await self.executor.sell(
                        symbol,
                        quantity=position["quantity"],
                        price=price,
                        strategy_id=genome.genome_id,
                    )

                    if order.status.value == "FILLED":
                        self.trades.append({
                            "genome_id": genome.genome_id,
                            "symbol": symbol,
                            "entry_price": position["entry_price"],
                            "exit_price": price,
                            "pnl_pct": pnl_pct,
                            "timestamp": timestamp,
                        })
                        position = None

        return self.trades

    async def _get_price_history(
        self,
        symbol: str,
        start_time: str,
        end_time: str,
    ) -> list[dict]:
        """获取价格历史 (模拟)"""
        # 简化: 生成随机价格序列
        import random
        from datetime import datetime, timedelta

        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)

        prices = []
        current_price = 50000  # 初始价格

        current = start
        while current < end:
            # 随机波动
            change = random.uniform(-0.02, 0.02)
            current_price *= (1 + change)

            prices.append({
                "price": current_price,
                "volume": random.uniform(100, 1000),
                "timestamp": current.isoformat(),
            })

            current += timedelta(hours=1)

        return prices


# ============ 便捷函数 ============

def create_ga_optimizer(
    population_size: int = 50,
    generations: int = 20,
) -> GeneticAlgorithm:
    """创建 GA 优化器"""
    return GeneticAlgorithm(
        population_size=population_size,
        generations=generations,
    )


async def quick_optimize(
    executor,
    symbol: str,
    population_size: int = 30,
    generations: int = 10,
) -> tuple[StrategyGenome, dict]:
    """快速优化策略"""
    ga = create_ga_optimizer(population_size, generations)
    replay = StrategyReplay(executor)

    def evaluate(genome):
        import asyncio
        return asyncio.run(replay.replay(
            genome,
            symbol,
            "2025-01-01T00:00:00",
            "2025-12-31T00:00:00",
        ))

    best_genome = await ga.run(evaluate)

    return best_genome, ga.get_stats()
