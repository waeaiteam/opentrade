"""
OpenTrade Data Sources

数据源连接器
"""

from opentrade.data_sources.ccxt import CCXTDataSource, create_ccxt_source
from opentrade.data_sources.glassnode import GlassnodeDataSource, create_glassnode_source
from opentrade.data_sources.fred import FREDDataSource, create_fred_source

__all__ = [
    "CCXTDataSource",
    "create_ccxt_source",
    "GlassnodeDataSource",
    "create_glassnode_source",
    "FREDDataSource",
    "create_fred_source",
]
