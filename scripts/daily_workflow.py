#!/usr/bin/env python3
"""
OpenTrade Daily Workflow Automation

每日自动化工作流：
1. 市场状态更新 (Fear & Greed Index)
2. 策略表现分析
3. 参数进化调整
4. 风险参数更新
5. 报告生成

Usage:
    python daily_workflow.py
    python daily_workflow.py --report  # 仅生成报告
    python daily_workflow.py --evolve  # 仅执行进化
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table


async def fetch_fear_greed_index() -> int:
    """获取恐惧贪婪指数"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.alternative.me/fng/?limit=1",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        return int(data["data"][0]["value"])
    except Exception as e:
        rprint(f"[yellow]⚠️ 获取 Fear Index 失败: {e}[/yellow]")
    return 50  # 默认中性


async def fetch_btc_price() -> float:
    """获取 BTC 价格"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data.get("price", 68000))
    except Exception:
        pass
    return 68000  # 默认价格


async def run_daily_workflow(
    evolve: bool = True,
    report_only: bool = False,
    verbose: bool = True,
) -> dict:
    """执行每日工作流"""
    
    workflow_start = datetime.utcnow()
    results = {
        "timestamp": workflow_start.isoformat(),
        "status": "running",
        "steps": {},
        "errors": [],
    }
    
    rprint(Panel(
        "[bold]🔄 OpenTrade 每日工作流[/bold]\n"
        f"开始时间: {workflow_start.isoformat()}",
        title="Daily Workflow",
        style="cyan"
    ))
    
    try:
        # Step 1: 获取市场数据
        rprint("\n[bold cyan]📊 Step 1: 获取市场数据[/bold cyan]")
        fear_index, btc_price = await asyncio.gather(
            fetch_fear_greed_index(),
            fetch_btc_price()
        )
        
        results["steps"]["market_data"] = {
            "fear_index": fear_index,
            "btc_price": btc_price,
            "status": "success",
        }
        
        rprint(f"   Fear Index: [bold]{fear_index}[/bold]/100")
        rprint(f"   BTC Price:  [bold]${btc_price:,.0f}[/bold]")
        
        # Step 2: 更新进化引擎
        if evolve:
            rprint("\n[bold cyan]🧬 Step 2: 策略进化[/bold cyan]")
            try:
                from opentrade.agents.evolution import get_evolution_engine
                
                engine = get_evolution_engine()
                
                # 更新市场状态
                engine.market_state.fear_greed_index = fear_index
                engine.market_state.btc_price = btc_price
                
                if not report_only:
                    # 执行进化
                    evolution_report = engine.evolve()
                    results["steps"]["evolution"] = {
                        "status": "success",
                        "report": evolution_report,
                    }
                    rprint("   进化完成 ✅")
                else:
                    rprint("   报告模式，跳过进化")
                
                # 风险参数
                risk_params = engine.get_risk_parameters()
                results["steps"]["risk_params"] = risk_params
                rprint(f"   风险模式: [bold]{risk_params['risk_mode']}[/bold]")
                rprint(f"   最大杠杆: [bold]{risk_params['max_leverage']}x[/bold]")
                
            except Exception as e:
                error_msg = f"进化失败: {e}"
                results["errors"].append(error_msg)
                rprint(f"   [red]❌ {error_msg}[/red]")
        
        # Step 3: 保存状态
        rprint("\n[bold cyan]💾 Step 3: 保存状态[/bold cyan]")
        data_dir = Path("/root/.opentrade/data")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        daily_state = {
            "date": workflow_start.date().isoformat(),
            "fear_index": fear_index,
            "btc_price": btc_price,
            "timestamp": workflow_start.isoformat(),
            "workflow_status": "completed",
        }
        
        state_file = data_dir / f"daily_state_{workflow_start.date()}.yaml"
        with open(state_file, "w") as f:
            yaml.dump(daily_state, f)
        
        results["steps"]["save_state"] = {
            "file": str(state_file),
            "status": "success",
        }
        rprint(f"   已保存至: {state_file.name} ✅")
        
        # Step 4: 生成报告
        rprint("\n[bold cyan]📋 Step 4: 生成报告[/bold cyan]")
        report = generate_report(results)
        results["steps"]["report"] = report
        
        # 保存报告
        report_file = data_dir / f"daily_report_{workflow_start.date()}.json"
        with open(report_file, "w") as f:
            # 移除不可序列化的对象
            serializable_results = {
                "timestamp": results["timestamp"],
                "status": results["status"],
                "steps": {
                    k: v for k, v in results["steps"].items()
                    if k != "evolution" or "report" in v
                }
            }
            import json
            json.dump(serializable_results, f, indent=2, default=str)
        
        results["steps"]["report_file"] = str(report_file)
        rprint(f"   报告已保存: {report_file.name} ✅")
        
        # 成功完成
        workflow_end = datetime.utcnow()
        duration = (workflow_end - workflow_start).total_seconds()
        
        results["status"] = "completed"
        results["duration_seconds"] = duration
        
        rprint(Panel(
            f"[green]✅ 每日工作流完成[/green]\n"
            f"耗时: {duration:.2f}秒\n"
            f"状态: {results['status']}",
            title="完成",
            style="green"
        ))
        
    except Exception as e:
        results["status"] = "failed"
        results["errors"].append(str(e))
        rprint(f"\n[red]❌ 工作流失败: {e}[/red]")
    
    return results


def generate_report(results: dict) -> dict:
    """生成报告"""
    fear = results["steps"].get("market_data", {}).get("fear_index", 50)
    btc = results["steps"].get("market_data", {}).get("btc_price", 0)
    risk = results["steps"].get("risk_params", {})
    
    return {
        "date": datetime.utcnow().date().isoformat(),
        "market": {
            "fear_index": fear,
            "sentiment": get_sentiment_label(fear),
            "btc_price": btc,
        },
        "risk": {
            "mode": risk.get("risk_mode", "neutral"),
            "max_leverage": risk.get("max_leverage", 2.0),
            "stablecoin_ratio": risk.get("stablecoin_ratio", 0.5),
        },
        "workflow": {
            "status": results["status"],
            "duration": results.get("duration_seconds", 0),
        },
    }


def get_sentiment_label(fear: int) -> str:
    """获取情绪标签"""
    if fear <= 25:
        return "Extreme Fear"
    elif fear <= 40:
        return "Fear"
    elif fear <= 60:
        return "Neutral"
    elif fear <= 75:
        return "Greed"
    else:
        return "Extreme Greed"


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenTrade Daily Workflow")
    parser.add_argument("--report", action="store_true", help="仅生成报告")
    parser.add_argument("--evolve", action="store_true", help="仅执行进化")
    parser.add_argument("--verbose", action="store_true", default=True)
    
    args = parser.parse_args()
    
    mode = "report" if args.report else "full"
    
    result = asyncio.run(run_daily_workflow(
        evolve=not args.report,
        report_only=args.report,
        verbose=args.verbose,
    ))
    
    # 退出码
    sys.exit(0 if result["status"] == "completed" else 1)


if __name__ == "__main__":
    main()

# 定时任务配置示例:
# 0 8 * * * /root/opentrade/scripts/daily_workflow.py  # 每天 UTC 8点执行
