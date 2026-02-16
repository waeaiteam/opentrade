"""
OpenTrade Doctor - 系统诊断

Usage:
    opentrade doctor [OPTIONS]

Options:
    --json          JSON 输出格式
    --verbose/-v    详细输出
    --fix           自动修复可修复的问题
    --help         显示帮助
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(name="doctor", help="系统诊断与健康检查")


class Doctor:
    """系统诊断医生"""

    def __init__(self, verbose: bool = False, fix: bool = False):
        self.verbose = verbose
        self.fix = fix
        self.results = []
        self.score = 100

    def check(self, name: str, func) -> dict:
        """执行检查并记录结果"""
        result = {"name": name, "status": "pending", "message": "", "fixable": False}

        try:
            output = func()
            if isinstance(output, dict):
                result.update(output)
            else:
                result["status"] = "✅" if output else "❌"
                result["message"] = str(output) if output else "检查失败"
        except Exception as e:
            result["status"] = "❌"
            result["message"] = str(e)

        self.results.append(result)

        # 计算分数
        if result["status"] == "❌":
            self.score -= 10
        elif result["status"] == "⚠️":
            self.score -= 5

        return result

    def check_python_version(self) -> dict:
        """检查 Python 版本"""
        import sys

        version = sys.version_info
        result = {
            "name": "Python 版本",
            "status": "✅",
            "message": f"{version.major}.{version.minor}.{version.micro}",
        }

        if version < (3, 10):
            result["status"] = "❌"
            result["message"] = f"需要 Python 3.10+，当前 {version.major}.{version.minor}"

        return result

    def check_dependencies(self) -> dict:
        """检查依赖包"""
        import subprocess

        try:
            result = subprocess.run(
                ["pip", "list", "--format=freeze"],
                capture_output=True,
                text=True,
            )

            required = [
                "opentrade",
                "ccxt",
                "pydantic",
                "pydantic-settings",
                "pyyaml",
                "rich",
                "typer",
                "sqlalchemy",
                "redis",
                "numpy",
                "pandas",
            ]

            installed = {line.split("==")[0] for line in result.stdout.strip().split("\n")}

            missing = [p for p in required if p not in installed]

            if missing:
                return {
                    "name": "依赖包",
                    "status": "❌",
                    "message": f"缺少: {', '.join(missing)}",
                    "fixable": True,
                    "fix_cmd": f"pip install {' '.join(missing)}",
                }

            return {
                "name": "依赖包",
                "status": "✅",
                "message": f"已安装 {len(installed)} 个包",
            }
        except Exception as e:
            return {"name": "依赖包", "status": "❌", "message": str(e)}

    def check_config(self) -> dict:
        """检查配置文件"""
        config_path = Path.home() / ".opentrade" / "config.yaml"

        if not config_path.exists():
            return {
                "name": "配置文件",
                "status": "⚠️",
                "message": "未找到配置文件，请运行 opentrade init",
                "fixable": True,
                "fix_cmd": "opentrade init",
            }

        try:
            import yaml
            with open(config_path) as f:
                config = yaml.safe_load(f)

            checks = []

            # 检查交易所配置
            exchange = config.get("exchange", {})
            if not exchange.get("api_key"):
                checks.append("交易所 API Key 未配置")

            # 检查 AI 配置
            ai = config.get("ai", {})
            if not ai.get("api_key"):
                checks.append("AI API Key 未配置")

            if checks:
                return {
                    "name": "配置文件",
                    "status": "⚠️",
                    "message": "; ".join(checks),
                }

            return {
                "name": "配置文件",
                "status": "✅",
                "message": f"路径: {config_path}",
            }
        except Exception as e:
            return {"name": "配置文件", "status": "❌", "message": str(e)}

    def check_database(self) -> dict:
        """检查数据库连接"""
        try:
            from opentrade.core.database import get_engine
            from sqlalchemy import text

            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                return {
                    "name": "PostgreSQL",
                    "status": "✅",
                    "message": "连接正常",
                }
        except Exception as e:
            return {
                "name": "PostgreSQL",
                "status": "❌",
                "message": str(e),
                "fixable": True,
                "fix_cmd": "确保 Docker 容器运行: docker compose up -d",
            }

    def check_redis(self) -> dict:
        """检查 Redis 连接"""
        try:
            from opentrade.core.config import get_config
            import redis

            config = get_config()
            r = redis.from_url(config.storage.redis_url)
            r.ping()
            return {
                "name": "Redis",
                "status": "✅",
                "message": "连接正常",
            }
        except Exception as e:
            return {
                "name": "Redis",
                "status": "❌",
                "message": str(e),
                "fixable": True,
                "fix_cmd": "确保 Redis 容器运行",
            }

    def check_exchange(self) -> dict:
        """检查交易所连接"""
        try:
            from opentrade.core.config import get_config
            import ccxt

            config = get_config()

            if not config.exchange.api_key:
                return {
                    "name": "交易所",
                    "status": "⚠️",
                    "message": "API Key 未配置，跳过连接测试",
                }

            exchange_class = getattr(ccxt, config.exchange.name)
            exchange = exchange_class({
                "apiKey": config.exchange.api_key,
                "secret": config.exchange.api_secret,
            })

            balance = exchange.fetch_balance()
            return {
                "name": f"交易所 ({config.exchange.name})",
                "status": "✅",
                "message": f"余额: {sum(float(v) for v in balance.get('total', {}).values()):.4f} USDT",
            }
        except Exception as e:
            return {
                "name": "交易所",
                "status": "❌",
                "message": str(e),
            }

    def check_ai_api(self) -> dict:
        """检查 AI API"""
        try:
            from opentrade.core.config import get_config
            import httpx

            config = get_config()

            if not config.ai.api_key:
                return {
                    "name": "AI API",
                    "status": "⚠️",
                    "message": "API Key 未配置",
                }

            # 简单测试调用
            base_url = config.ai.base_url or "https://api.deepseek.com/v1"
            headers = {"Authorization": f"Bearer {config.ai.api_key}"}

            response = httpx.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": "hi"}]},
                timeout=10.0,
            )

            if response.status_code == 200:
                return {
                    "name": "AI API",
                    "status": "✅",
                    "message": config.ai.model,
                }
            else:
                return {
                    "name": "AI API",
                    "status": "❌",
                    "message": f"HTTP {response.status_code}",
                }
        except Exception as e:
            return {
                "name": "AI API",
                "status": "❌",
                "message": str(e),
            }

    def check_disk_space(self) -> dict:
        """检查磁盘空间"""
        import shutil

        usage = shutil.disk_usage("/")

        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)

        if free_gb < 1:
            return {
                "name": "磁盘空间",
                "status": "⚠️",
                "message": f"剩余 {free_gb:.1f} GB",
            }

        return {
            "name": "磁盘空间",
            "status": "✅",
            "message": f"剩余 {free_gb:.1f} / {total_gb:.1f} GB",
        }

    def check_port(self, port: int = 8000) -> dict:
        """检查端口占用"""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)

        try:
            result = sock.connect_ex(("127.0.0.1", port))
            if result == 0:
                return {
                    "name": f"端口 {port}",
                    "status": "✅",
                    "message": "已被占用 (服务可能正在运行)",
                }
            else:
                return {
                    "name": f"端口 {port}",
                    "status": "✅",
                    "message": "空闲",
                }
        except Exception as e:
            return {
                "name": f"端口 {port}",
                "status": "❌",
                "message": str(e),
            }
        finally:
            sock.close()

    def run_all(self):
        """运行所有检查"""
        print("\n[bold]🔍 OpenTrade 系统诊断[/bold]\n")

        # 基础检查
        self.check("Python 版本", self.check_python_version)
        self.check("依赖包", self.check_dependencies)
        self.check("配置文件", self.check_config)

        # 服务检查
        self.check("PostgreSQL", self.check_database)
        self.check("Redis", self.check_redis)

        # 外部服务
        self.check("交易所连接", self.check_exchange)
        self.check("AI API", self.check_ai_api)

        # 系统检查
        self.check("磁盘空间", self.check_disk_space)
        self.check("端口 8000", lambda: self.check_port(8000))
        self.check("端口 18790", lambda: self.check_port(18790))

        return self.results

    def print_report(self):
        """打印报告"""
        console = Console()

        # 计算健康分数
        score = max(0, self.score)

        # 状态
        if score >= 90:
            status = "🟢 健康"
        elif score >= 70:
            status = "🟡 正常"
        else:
            status = "🔴 需要关注"

        # 汇总表格
        table = Table(title="诊断结果", show_header=True)
        table.add_column("检查项", style="cyan")
        table.add_column("状态", width=8)
        table.add_column("说明", style="dim")

        for r in self.results:
            status_icon = r["status"]
            table.add_row(r["name"], status_icon, r["message"])

        console.print(table)

        # 可修复项
        fixable = [r for r in self.results if r.get("fixable")]
        if fixable:
            print("\n[bold]🔧 可修复项:[/bold]")
            for r in fixable:
                cmd = r.get("fix_cmd", "")
                print(f"   • {r['name']}: {cmd}")

        # 总结
        print(Panel(
            f"[bold]健康评分: {score}/100[/bold]\n"
            f"状态: {status}\n"
            f"时间: {datetime.now().isoformat()}",
            title="诊断报告",
        ))

        return score


def output_json(results: list, score: int):
    """JSON 输出"""
    import json

    output = {
        "timestamp": datetime.now().isoformat(),
        "score": score,
        "results": results,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


@app.command()
def main(
    json_output: bool = typer.Option(False, "--json", help="JSON 输出"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="详细输出"),
    fix: bool = typer.Option(False, "--fix", help="自动修复"),
):
    """运行系统诊断"""
    doctor = Doctor(verbose=verbose, fix=fix)
    results = doctor.run_all()
    score = doctor.score

    if json_output:
        output_json(results, score)
    else:
        doctor.print_report()

    # 退出码
    if score < 70:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
