from .client import BinanceClient
from .config import Config

class UMMarketClient(BinanceClient):
    def __init__(self):
        super().__init__(base_url=Config.FAPI_URL)

    def get_ticker_price(self, symbol):
        """
        最新价格V2
        GET /fapi/v2/ticker/price
        """
        params = {'symbol': symbol}
        return self.get('/fapi/v2/ticker/price', params=params, signed=False)
    
    def get_depth(self, symbol, limit=5):
        """
        深度信息
        GET /fapi/v1/depth
        """
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return self.get('/fapi/v1/depth', params=params, signed=False)
