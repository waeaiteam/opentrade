"""
OpenTrade Data Sources - FRED (Federal Reserve Economic Data)

宏观经济数据
"""

from datetime import datetime
from typing import Any
from opentrade.data.service import DataConnector, DataSource


class FREDDataSource(DataConnector):
    """FRED 宏观经济数据源"""

    def __init__(self, api_key: str = ""):
        super().__init__(DataSource.FRED)
        self.api_key = api_key
        self.base_url = "https://api.stlouisfed.org/fred"

    async def fetch_series(
        self,
        series_id: str,
        observation_start: datetime = None,
        observation_end: datetime = None,
    ) -> list[dict]:
        """获取经济数据序列"""
        import httpx

        params = {
            'api_key': self.api_key,
            'file_type': 'json',
            'series_id': series_id,
        }

        if observation_start:
            params['observation_start'] = observation_start.strftime('%Y-%m-%d')
        if observation_end:
            params['observation_end'] = observation_end.strftime('%Y-%m-%d')

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/series/observations",
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                return data.get('observations', [])
        except Exception as e:
            print(f"[Data] FRED error: {e}")
            return []

    async def get_cpi(self) -> dict:
        """获取 CPI 数据"""
        observations = await self.fetch_series("CPIAUCSL")
        if observations:
            return {
                'value': float(observations[-1].get('value', 0)),
                'date': observations[-1].get('date'),
            }
        return {'value': 0, 'date': None}

    async def get_unemployment_rate(self) -> dict:
        """获取失业率"""
        observations = await self.fetch_series("UNRATE")
        if observations:
            return {
                'value': float(observations[-1].get('value', 0)),
                'date': observations[-1].get('date'),
            }
        return {'value': 0, 'date': None}

    async def get_federal_funds_rate(self) -> dict:
        """获取联邦基金利率"""
        observations = await self.fetch_series("FEDFUNDS")
        if observations:
            return {
                'value': float(observations[-1].get('value', 0)),
                'date': observations[-1].get('date'),
            }
        return {'value': 0, 'date': None}

    async def get_gdp_growth(self) -> dict:
        """获取 GDP 增长率"""
        observations = await self.fetch_series("GDPC1")
        if observations:
            return {
                'value': float(observations[-1].get('value', 0)),
                'date': observations[-1].get('date'),
            }
        return {'value': 0, 'date': None}

    def get_available_series(self) -> dict:
        """获取可用数据序列"""
        return {
            'macro': ['CPIAUCSL', 'UNRATE', 'FEDFUNDS', 'GDPC1'],
            'interest': ['DGS10', 'DGS2', 'DGS30'],
            'housing': ['HOUST', 'CSUSHPISA'],
        }


def create_fred_source(api_key: str = "") -> FREDDataSource:
    """创建 FRED 数据源"""
    return FREDDataSource(api_key=api_key)
