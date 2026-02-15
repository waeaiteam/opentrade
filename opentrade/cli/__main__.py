"""OpenTrade CLI 主入口"""

import sys
from pathlib import Path

# 确保能找到 opentrade 包
_package_dir = Path(__file__).parent
if _package_dir.parent not in sys.path:
    sys.path.insert(0, str(_package_dir.parent))


def main():
    """CLI 入口点"""
    try:
        from .cli import app
        from .cli.utils import handle_exceptions, setup_logging
        
        setup_logging()
        app()
    except KeyboardInterrupt:
        print("\n\n👋 再见！祝交易顺利！")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
