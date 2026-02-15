# OpenTrade 架构设计方案

## 项目概述
开源 AI 加密货币自主交易系统

---

## 一、系统架构 (总览)

```
┌─────────────────────────────────────────────────────────────────┐
│                        OpenTrade 系统                            │
├─────────────────────────────────────────────────────────────────┤
│  前端 (Web/Telegram/CLI)                                       │
├─────────────────────────────────────────────────────────────────┤
│  网关层 (WebSocket + REST API)                                 │
├──────────────────────┬─────────────────────┬───────────────────┤
│   交易服务           │   AI 服务           │   数据服务        │
│   - TradeExecutor   │   - Coordinator     │   - DataService   │
│   - StrategyService │   - Market Agent    │   - Backtest     │
│   - BacktestService │   - Strategy Agent  │   - Notification │
│                     │   - Risk Agent       │                   │
│                     │   - OnChain Agent   │                   │
│                     │   - Sentiment Agent │                   │
│                     │   - Macro Agent     │                   │
├──────────────────────┴─────────────────────┴───────────────────┤
│  插件层 (CCXT 交易所插件)                                       │
├──────────────────────┬─────────────────────┬───────────────────┤
│  数据存储            │   缓存               │   消息队列        │
│  - PostgreSQL        │   - Redis            │   - (可选)        │
│  - TimescaleDB      │                     │                   │
└──────────────────────┴─────────────────────┴───────────────────┘
```

---

## 二、核心模块详解

### 2.1 CLI 命令行 (12个命令)

```bash
opentrade init          # 初始化配置
opentrade gateway        # 启动网关服务
opentrade trade         # 启动交易 (paper/live)
opentrade backtest      # 回测策略
opentrade strategy      # 策略管理
opentrade plugin        # 插件管理
opentrade config        # 配置管理
opentrade doctor        # 系统诊断
opentrade update        # 更新检查
```

### 2.2 AI Agents (7个协作 Agent)

```
Coordinator Agent (协调者)
├── Market Agent (技术分析)
├── Strategy Agent (策略分析)
├── Risk Agent (风险控制)
├── OnChain Agent (链上数据)
├── Sentiment Agent (情绪分析)
└── Macro Agent (宏观分析)
```

**决策流程:**
1. 各 Agent 并行分析市场
2. Coordinator 综合所有信号
3. 生成最终交易决策 (BUY/SELL/HOLD)
4. Risk Agent 最终校验
5. 执行交易

### 2.3 交易所支持 (45+ 交易所)

```python
# 插件架构
ExchangePlugin (基类)
├── CCXTExchangePlugin (通用)
├── HyperliquidPlugin (专用)
├── BinancePlugin (专用)
└── ...

# 支持的交易所
- Binance, Bybit, OKX, KuCoin
- Hyperliquid, Bitget, Gate
- MEXC, CoinEx, Huobi
- (CCXT 支持的全部)
```

### 2.4 数据模型

```
Trade (交易记录)
├── symbol, side, action, status
├── entry_price, exit_price, quantity
├── pnl, pnl_percent, fee
└── strategy_id, created_at

Position (持仓)
├── symbol, side, status
├── size, entry_price, mark_price
├── stop_loss, take_profit
├── unrealized_pnl
└── opened_at, updated_at

Strategy (策略)
├── name, version, type
├── parameters (JSON)
├── performance metrics
└── status, created_at
```

---

## 三、技术栈

| 层级 | 技术选型 |
|------|----------|
| 语言 | Python 3.11+, Node.js 22+ |
| Web 框架 | FastAPI + Next.js |
| 数据库 | PostgreSQL 15 + TimescaleDB |
| 缓存 | Redis 7 |
| 任务调度 | APScheduler |
| 交易所对接 | CCXT |
| 构建工具 | setuptools + pnpm + turbo |
| 容器化 | Docker + Docker Compose |
| CI/CD | GitHub Actions |

---

## 四、部署架构

### 4.1 Docker Compose

```yaml
services:
  opentrade:       # 主服务 (端口 18790, 3000)
  postgres:        # 数据库 (端口 5432)
  redis:           # 缓存 (端口 6379)
  pgadmin:         # 数据库管理 (端口 5050)
```

### 4.2 端口说明

| 端口 | 服务 | 用途 |
|------|------|------|
| 18790 | Gateway WebSocket | 控制平面 |
| 3000 | Web UI | 仪表盘 |
| 5432 | PostgreSQL | 数据存储 |
| 6379 | Redis | 缓存 |
| 5050 | pgAdmin | 数据库管理 |

---

## 五、交易流程

```
1. 数据采集
   └── DataService 获取 OHLCV + 订单簿 + 资金费率

2. AI 分析
   └── 7个 Agents 并行分析 (技术/链上/情绪/宏观)

3. 决策生成
   └── Coordinator 综合信号 → 交易决策

4. 风控校验
   └── RiskAgent 检查仓位/杠杆/止损

5. 订单执行
   └── TradeExecutor → CCXT → 交易所

6. 通知
   └── Telegram/邮件/Push 通知

7. 记录
   └── PostgreSQL 保存交易记录
```

---

## 六、风险控制

### 6.1 硬性规则

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_position_pct | 10% | 单笔最大仓位 |
| max_leverage | 3x | 最大杠杆 |
| max_daily_loss_pct | 5% | 每日止损线 |
| max_open_positions | 3 | 最大持仓数 |
| stop_loss_pct | 5% | 止损比例 |
| take_profit_pct | 10% | 止盈比例 |

### 6.2 动态风控

- Kelly Criterion 仓位计算
- 波动率自适应调整
- 情绪极端时降低仓位
- 宏观风险事件暂停交易

---

## 七、策略进化

```
每日复盘流程:
1. 记录所有交易
2. 计算策略绩效 (胜率/夏普/回撤)
3. 遗传算法变异参数
4. 回测验证
5. 优胜劣汰
6. 保存新版本
```

---

## 八、文件结构

```
opentrade/
├── README.md              # 设计文档 (本文档源)
├── pyproject.toml         # Python 包配置
├── Dockerfile             # Docker 构建
├── docker-compose.yml     # 部署配置
├── .github/workflows/ci.yml  # CI/CD
├── opentrade/
│   ├── __init__.py
│   ├── agents/            # AI Agents (8个)
│   ├── services/          # 服务模块 (6个)
│   ├── plugins/           # 交易所插件
│   ├── models/            # 数据模型
│   ├── core/              # 核心配置/数据库
│   ├── cli/               # 命令行
│   └── web/               # Web 配置
└── tests/                 # 单元测试
```

---

## 九、快速开始

### pip 安装

```bash
pip install opentrade
opentrade init
opentrade gateway
opentrade trade --mode paper
```

### Docker 部署

```bash
git clone https://github.com/opentrade-ai/opentrade.git
cd opentrade
docker-compose up -d
# 访问 http://localhost:3000
```

---

## 十、许可证

MIT License

---

最后更新: 2026-02-15
项目: https://github.com/opentrade-ai/opentrade
