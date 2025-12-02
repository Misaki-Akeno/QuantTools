from .client import BinanceClient
from .config import Config

class UMAccountClient(BinanceClient):
    def __init__(self):
        super().__init__(base_url=Config.PAPI_URL)

    # --- Account Interfaces ---

    def get_balance(self):
        """
        查询账户余额 (USER-DATA)
        GET /papi/v1/balance
        """
        return self.get('/papi/v1/balance', signed=True)

    def get_account_info(self):
        """
        查询账户信息 (USER-DATA)
        GET /papi/v1/account
        """
        return self.get('/papi/v1/account', signed=True)

    def get_position_mode(self):
        """
        查询UM持仓模式 (USER-DATA)
        GET /papi/v1/um/positionSide/dual
        """
        return self.get('/papi/v1/um/positionSide/dual', signed=True)

    def change_position_mode(self, dualSidePosition):
        """
        更改UM持仓模式 (TRADE)
        POST /papi/v1/um/positionSide/dual
        """
        params = {
            'dualSidePosition': dualSidePosition
        }
        return self.post('/papi/v1/um/positionSide/dual', params=params, signed=True)