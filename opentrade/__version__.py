"""OpenTrade 版本信息"""

__version__ = "1.0.0a1"
__author__ = "OpenTrade Contributors"
__email__ = "contributors@opentrade.ai"
__license__ = "MIT"

# 版本信息
VERSION_INFO = tuple(int(x) for x in __version__.split("-")[0].split("."))

# 元数据
METADATA = {
    "version": __version__,
    "author": __author__,
    "email": __email__,
    "license": __license__,
    "homepage": "https://opentrade.ai",
    "repository": "https://github.com/opentrade-ai/opentrade",
    "documentation": "https://docs.opentrade.ai",
    "changelog": "https://github.com/opentrade-ai/opentrade/blob/main/CHANGELOG.md",
    "issues": "https://github.com/opentrade-ai/opentrade/issues",
    "discord": "https://discord.gg/opentrade",
}
