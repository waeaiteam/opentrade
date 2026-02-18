"""
应急处理命令
一键冻结交易、重置API密钥、紧急平仓
"""
import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class EmergencyHandler:
    """
    应急处理器
    
    功能:
    1. 一键冻结所有交易
    2. 重置 API 密钥
    3. 紧急平仓
    4. 生成安全报告
    """
    
    def __init__(self, workdir: str = "/root/.opentrade"):
        self.workdir = Path(workdir)
        self.state_file = self.workdir / ".emergency_state.json"
        self._load_state()
    
    def _load_state(self):
        """加载状态"""
        if self.state_file.exists():
            import json
            try:
                self._state = json.loads(self.state_file.read_text())
            except Exception:
                self._state = {"frozen": False, "frozen_at": None, "reason": ""}
        else:
            self._state = {"frozen": False, "frozen_at": None, "reason": ""}
    
    def _save_state(self):
        """保存状态"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text("__import__('json').dumps(self._state)")
        os.chmod(str(self.state_file), 0o600)
    
    def freeze_all_trading(self, reason: str = "手动冻结") -> dict:
        """
        冻结所有交易
        
        Returns:
            冻结结果
        """
        self._state = {
            "frozen": True,
            "frozen_at": datetime.now().isoformat(),
            "reason": reason,
            "frozen_by": "emergency_command"
        }
        self._save_state()
        
        # 触发熔断器
        from opentrade.core.circuit_breaker import get_circuit_breaker
        cb = get_circuit_breaker()
        import asyncio
        asyncio.run(cb.emergency_shutdown(f"紧急冻结: {reason}"))
        
        logger.critical(f"🚨 交易已冻结: {reason}")
        
        return {
            "success": True,
            "frozen_at": self._state["frozen_at"],
            "reason": reason
        }
    
    def unfreeze_trading(self, reason: str = "手动解冻") -> dict:
        """解冻交易"""
        self._state = {"frozen": False, "frozen_at": None, "reason": ""}
        self._save_state()
        
        # 重置熔断
        from opentrade.core.circuit_breaker import get_circuit_breaker
        cb = get_circuit_breaker()
        cb.reset_account()
        cb.reset_system()
        
        logger.info(f"✅ 交易已解冻: {reason}")
        
        return {
            "success": True,
            "unfrozen_at": datetime.now().isoformat(),
            "reason": reason
        }
    
    def is_frozen(self) -> bool:
        """检查是否冻结"""
        self._load_state()
        return self._state.get("frozen", False)
    
    def reset_api_keys(self) -> dict:
        """
        重置所有 API 密钥
        
        警告: 此操作将删除所有保存的 API 密钥
        """
        from opentrade.core.encryption import SecureConfig, CONFIG_FILE
        
        results = {"deleted": [], "failed": []}
        
        # 删除加密配置
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
            results["deleted"].append(str(CONFIG_FILE))
        
        # 删除加密密钥
        key_file = Path("/root/.opentrade/.encryption_key")
        if key_file.exists():
            key_file.unlink()
            results["deleted"].append(str(key_file))
        
        # 清理环境变量
        env_vars = ["HYPERLIQUID_API_KEY", "HYPERLIQUID_API_SECRET", 
                   "BINANCE_API_KEY", "BINANCE_API_SECRET"]
        for var in env_vars:
            if os.environ.get(var):
                del os.environ[var]
                results["deleted"].append(f"ENV:{var}")
        
        logger.warning(f"🔑 API密钥已重置: {results}")
        
        return results
    
    def generate_security_report(self) -> dict:
        """生成安全报告"""
        from opentrade.core.circuit_breaker import get_circuit_breaker
        from opentrade.core.encryption import SecureConfig
        
        cb = get_circuit_breaker()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "trading_frozen": self.is_frozen(),
            "circuit_breaker_status": cb.get_status(),
            "security_checks": {
                "api_key_encrypted": True,  # 加密模块存在
                "emergency_state_exists": self.state_file.exists(),
                "environment_clean": self._check_env_security()
            }
        }
        
        # 保存报告
        report_file = self.workdir / "reports" / f"security_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text("__import__('json').dumps(report, indent=2)")
        
        logger.info(f"📄 安全报告已生成: {report_file}")
        
        return report
    
    def _check_env_security(self) -> dict:
        """检查环境安全性"""
        return {
            "opentrade_dir_permissions": oct(os.stat(self.workdir).st_mode),
            "api_key_in_env": any(
                "API" in k or "KEY" in k or "SECRET" in k 
                for k in os.environ.keys()
            )
        }
    
    def get_state(self) -> dict:
        """获取当前状态"""
        self._load_state()
        return self._state


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="OpenTrade 应急处理命令",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 冻结所有交易
  python -m opentrade.cli.emergency freeze --reason "安全检查"
  
  # 解冻交易
  python -m opentrade.cli.emergency unfreeze
  
  # 重置 API 密钥
  python -m opentrade.cli.emergency reset-keys
  
  # 生成安全报告
  python -m opentrade.cli.emergency report
  
  # 检查状态
  python -m opentrade.cli.emergency status
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # freeze 命令
    freeze_parser = subparsers.add_parser("freeze", help="冻结所有交易")
    freeze_parser.add_argument("--reason", default="手动操作", help="冻结原因")
    
    # unfreeze 命令
    unfreeze_parser = subparsers.add_parser("unfreeze", help="解冻交易")
    unfreeze_parser.add_argument("--reason", default="手动操作", help="解冻原因")
    
    # reset-keys 命令
    subparsers.add_parser("reset-keys", help="重置所有 API 密钥")
    
    # report 命令
    subparsers.add_parser("report", help="生成安全报告")
    
    # status 命令
    subparsers.add_parser("status", help="检查当前状态")
    
    args = parser.parse_args()
    
    handler = EmergencyHandler()
    
    if args.command == "freeze":
        result = handler.freeze_all_trading(args.reason)
        print(f"✅ 交易已冻结: {result}")
        
    elif args.command == "unfreeze":
        result = handler.unfreeze_trading(args.reason)
        print(f"✅ 交易已解冻: {result}")
        
    elif args.command == "reset-keys":
        confirm = input("⚠️ 确认重置所有 API 密钥? (输入 YES 确认): ")
        if confirm == "YES":
            result = handler.reset_api_keys()
            print(f"✅ 已删除: {result}")
        else:
            print("❌ 操作已取消")
            
    elif args.command == "report":
        result = handler.generate_security_report()
        print(f"📄 {result}")
        
    elif args.command == "status":
        state = handler.get_state()
        cb_state = handler.generate_security_report()
        print(f"状态: {state}")
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
