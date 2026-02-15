[English](README.md) | [中文](README_CN.md) | [文档](https://docs.opentrade.ai)

# OpenTrade - 开源 AI 交易系统

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/opentrade-ai/opentrade?style=for-the-badge)](https://github.com/opentrade-ai/opentrade/stargazers)
[![License](https://img.shields.io/github/license/opentrade-ai/opentrade?style=for-the-badge)](https://github.com/opentrade-ai/opentrade/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=for-the-badge)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-22%2B-green?style=for-the-badge)](https://nodejs.org/)

**自主进化 AI 交易代理 | 7×24 小时运行 | 多交易所支持**

</div>

## ✨ 特性

- **🤖 自主 AI 交易**: 多代理协作 + 持续进化
- **📊 全市场覆盖**: 46+ 交易所 + 链上数据 + 宏观数据
- **🛡️ 企业级安全**: 硬止损 + 多签验证 + 加密存储
- **🌐 多平台支持**: Web + Telegram + CLI + API
- **🧩 插件架构**: 策略/数据源/通知插件

## 🚀 快速开始

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

### 开发模式

```bash
git clone https://github.com/opentrade-ai/opentrade.git
cd opentrade
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

## 📁 项目结构

```
opentrade/
├── apps/          # CLI/Web/Telegram/Mobile 应用
├── packages/core/ # Python 核心库
├── packages/sdk/  # 开发者 SDK
├── plugins/       # 策略/数据源/通知插件
├── skills/        # Agent Skills
├── docs/          # 文档
└── tests/        # 测试
```

## 📦 包管理器

**Python (pip)**:
```bash
pip install opentrade           # 核心包
pip install opentrade[cli]     # CLI 工具
pip install opentrade[all]     # 全部功能
pip install opentrade[dev]     # 开发依赖
```

**Node.js (pnpm)**:
```bash
pnpm add opentrade-web         # Web 面板
pnpm add opentrade-sdk         # TypeScript SDK
```

## 🔧 CLI 命令

```bash
opentrade init                 # 初始化
opentrade gateway              # 启动网关
opentrade trade --mode live    # 实盘交易
opentrade backtest             # 回测
opentrade strategy list        # 策略管理
opentrade plugin install       # 安装插件
```

## 🧩 插件开发

```python
from opentrade.plugins.strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    name = "my_strategy"
    
    async def generate_signal(self, market_data):
        return {"action": "BUY", "symbol": "BTC/USDT"}
```

## 🤝 贡献

欢迎提交 Issue 和 PR！

## ⚠️ 风险提示

加密货币交易存在重大风险，请仅使用能承受损失的资金。

---

<div align="center">
如果对你有帮助，请 ⭐ Star 支持！
</div>
