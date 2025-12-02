from .client import BinanceClient
from .config import Config

class UMFuturesClient(BinanceClient):
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

    # --- Trade Interfaces ---

    def new_order(self, symbol, side, type, quantity, price=None, timeInForce=None, **kwargs):
        """
        UM下单 (TRADE)
        POST /papi/v1/um/order
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': type,
            'quantity': quantity,
        }
        if price:
            params['price'] = price
        if timeInForce:
            params['timeInForce'] = timeInForce
        
        params.update(kwargs)
        
        return self.post('/papi/v1/um/order', params=params, signed=True)

    def cancel_order(self, symbol, orderId=None, origClientOrderId=None):
        """
        撤销UM订单 (TRADE)
        DELETE /papi/v1/um/order
        """
        params = {
            'symbol': symbol
        }
        if orderId:
            params['orderId'] = orderId
        if origClientOrderId:
            params['origClientOrderId'] = origClientOrderId
            
        return self.delete('/papi/v1/um/order', params=params, signed=True)
    
    def cancel_all_orders(self, symbol):
        """
        撤销所有UM订单 (TRADE)
        DELETE /papi/v1/um/allOpenOrders
        """
        params = {
            'symbol': symbol
        }
        return self.delete('/papi/v1/um/allOpenOrders', params=params, signed=True)

    def get_open_orders(self, symbol=None):
        """
        查询当前UM挂单 (USER-DATA)
        GET /papi/v1/um/openOrders
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self.get('/papi/v1/um/openOrders', params=params, signed=True)
