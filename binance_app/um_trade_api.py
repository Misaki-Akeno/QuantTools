from .client import BinanceClient
from .config import Config

class UMTradeClient(BinanceClient):
    def __init__(self):
        super().__init__(base_url=Config.PAPI_URL)

    # --- Trade Interfaces ---

    def new_order(self, symbol, side, type, quantity=None, price=None, positionSide=None, timeInForce=None, 
                  reduceOnly=None, newClientOrderId=None, newOrderRespType=None, priceMatch=None, 
                  selfTradePreventionMode=None, goodTillDate=None, **kwargs):
        """
        UM下单 (TRADE)
        POST /papi/v1/um/order
        
        :param symbol: 交易对 (必需)
        :param side: 订单方向 BUY, SELL (必需)
        :param type: 订单类型 LIMIT, MARKET 等 (必需)
        :param quantity: 下单数量 (LIMIT, MARKET 必需)
        :param price: 委托价格 (LIMIT 必需)
        :param positionSide: 持仓方向 BOTH, LONG, SHORT (双向持仓必填)
        :param timeInForce: 有效方式 GTC, IOC, FOK, GTX, GTD (LIMIT 必需)
        :param reduceOnly: 只减仓 true/false (非双开模式下默认false)
        :param newClientOrderId: 用户自定义订单号
        :param newOrderRespType: 响应类型 ACK, RESULT
        :param priceMatch: 价格匹配模式 (不能与 price 同时传)
        :param selfTradePreventionMode: 自成交保护模式
        :param goodTillDate: 自动取消时间 (TIF为GTD时必传)
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': type,
        }
        
        if quantity is not None:
            params['quantity'] = quantity
        if price is not None:
            params['price'] = price
        if positionSide:
            params['positionSide'] = positionSide
        if timeInForce:
            params['timeInForce'] = timeInForce
        if reduceOnly is not None:
            params['reduceOnly'] = reduceOnly
        if newClientOrderId:
            params['newClientOrderId'] = newClientOrderId
        if newOrderRespType:
            params['newOrderRespType'] = newOrderRespType
        if priceMatch:
            params['priceMatch'] = priceMatch
        if selfTradePreventionMode:
            params['selfTradePreventionMode'] = selfTradePreventionMode
        if goodTillDate:
            params['goodTillDate'] = goodTillDate
        
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