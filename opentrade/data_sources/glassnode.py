"""
OpenTrade Data Sources - Glassnode Integration

链上数据: 持仓、交易所流入流出等
"""

from datetime import datetime
from typing import Any
from opentrade.data.service import DataConnector, DataSource


class GlassnodeDataSource(DataConnector):
    """Glassnode 链上数据源"""

    def __init__(self, api_key: str = ""):
        super().__init__(DataSource.GLASSNODE)
        self.api_key = api_key
        self.base_url = "https://api.glassnode.com/v1"

    async def fetch_onchain_metrics(
        self,
        asset: str = "BTC",
        metric: str = "market_cap",
        since: int = None,
        until: int = None,
    ) -> list[dict]:
        """获取链上指标"""
        import httpx

        params = {
            'api_key': self.api_key,
            'asset': asset,
            'metric': metric,
        }

        if since:
            params['since'] = since
        if until:
            params['until'] = until

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/{metric}",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"[Data] Glassnode error: {e}")
            return []

    async def get_exchange_flow(
        self,
        asset: str = "BTC",
        flow: str = "net",
    ) -> dict:
        """获取交易所净流入/流出"""
        metrics = await self.fetch_onchain_metrics(
            asset=asset,
            metric=f"flow_{flow}_exchange",
        )

        if metrics:
            return {
                'value': metrics[-1].get('v', 0),
                'timestamp': metrics[-1].get('t', 0),
            }
        return {'value': 0, 'timestamp': 0}

    async def get_whale_activity(
        self,
        asset: str = "BTC",
        threshold: int = 100,
    ) -> dict:
        """获取大额交易活动"""
        metrics = await self.fetch_onchain_metrics(
            asset=asset,
            metric=f"transactions_greater_than_{threshold}_count",
        )

        if metrics:
            return {
                'count': metrics[-1].get('v', 0),
                'timestamp': metrics[-1].get('t', 0),
            }
        return {'count': 0, 'timestamp': 0}


def create_glassnode_source(api_key: str = "") -> GlassnodeDataSource:
    """创建 Glassnode 数据源"""
    return GlassnodeDataSource(api_key=api_key)
