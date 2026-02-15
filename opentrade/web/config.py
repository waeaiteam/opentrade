"""
OpenTrade Web 配置
"""


from pydantic import BaseModel


class WebSettings(BaseModel):
    """Web 配置"""
    title: str = "OpenTrade"
    theme: str = "dark"
    language: str = "zh-CN"
    refresh_interval: int = 5  # 秒
    chart_interval: str = "1h"  # K线周期


settings = WebSettings()
