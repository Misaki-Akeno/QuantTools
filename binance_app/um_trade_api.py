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
        
        [
            {
                "avgPrice": "0.00000",
                "clientOrderId": "abc",
                "cumQuote": "0",
                "executedQty": "0",
                "orderId": 1917641,
                "origQty": "0.40",
                "origType": "LIMIT",
                "price": "0",
                "reduceOnly": false,
                "side": "BUY",
                "positionSide": "SHORT",
                "status": "NEW",
                "symbol": "BTCUSDT",
                "time": 1579276756075,            
                "timeInForce": "GTC",
                "type": "LIMIT",
                "updateTime": 1579276756075，
                "selfTradePreventionMode": "NONE", 
                "goodTillDate": 0,
                "priceMatch": "NONE"     
            }
        ]
        """
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self.get('/papi/v1/um/openOrders', params=params, signed=True)

    def new_conditional_order(self, symbol, side, strategyType, positionSide=None, timeInForce=None, 
                              quantity=None, reduceOnly=None, price=None, workingType=None, 
                              priceProtect=None, newClientStrategyId=None, stopPrice=None, 
                              activationPrice=None, callbackRate=None, priceMatch=None, 
                              selfTradePreventionMode=None, goodTillDate=None, **kwargs):
        """
        UM条件单下单 (TRADE)
        POST /papi/v1/um/conditional/order
        
        请求权重: 1
        
        :param symbol: 交易对 (必需)
        :param side: 方向 BUY, SELL (必需)
        :param strategyType: 条件单类型 "STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET" (必需)
        :param positionSide: 持仓方向 BOTH, LONG, SHORT (单向持仓模式下非必填，默认且仅可填BOTH; 双向持仓模式下必填,且仅可选择 LONG 或 SHORT)
        :param timeInForce: 有效方式 GTC, IOC, FOK, GTX, GTD (STOP/TAKE_PROFIT时可选，默认GTC)
        :param quantity: 下单数量 (STOP/TAKE_PROFIT时必需)
        :param reduceOnly: 只减仓 true/false (非双开模式下默认false；双开模式下不接受此参数)
        :param price: 委托价格 (STOP/TAKE_PROFIT时必需)
        :param workingType: stopPrice 触发类型 MARK_PRICE(标记价格), CONTRACT_PRICE(合约最新价). 默认 CONTRACT_PRICE
        :param priceProtect: 条件单触发保护 "TRUE","FALSE", 默认"FALSE". 仅 STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET 需要此参数
        :param newClientStrategyId: 用户自定义的订单号，不可以重复出现在挂单中。如空缺系统会自动赋值。
        :param stopPrice: 触发价格 (STOP/STOP_MARKET/TAKE_PROFIT/TAKE_PROFIT_MARKET时必需)
        :param activationPrice: TRAILING_STOP_MARKET 单使用，默认标记价格
        :param callbackRate: TRAILING_STOP_MARKET 单使用, 最小0.1, 最大5，1代表1%
        :param priceMatch: 价格匹配模式 OPPONENT/OPPONENT_5/OPPONENT_10/OPPONENT_20/QUEUE/QUEUE_5/QUEUE_10/QUEUE_20；不能与price同时传
        :param selfTradePreventionMode: 自成交保护模式 NONE/EXPIRE_TAKER/EXPIRE_MAKER/EXPIRE_BOTH；默认NONE
        :param goodTillDate: TIF为GTD时订单的自动取消时间，传入的时间戳仅保留秒级精度，毫秒级部分会被自动忽略，时间戳需大于当前时间+600s且小于253402300799000
        
        根据 strategyType 的不同，某些参数强制要求：
        - STOP/TAKE_PROFIT: quantity, price, stopPrice
        - STOP_MARKET/TAKE_PROFIT_MARKET: stopPrice
        - TRAILING_STOP_MARKET: callbackRate
        
        条件单触发逻辑：
        - STOP, STOP_MARKET 止损单: 买入(最新合约价格/标记价格 >= stopPrice), 卖出(最新合约价格/标记价格 <= stopPrice)
        - TAKE_PROFIT, TAKE_PROFIT_MARKET 止盈单: 买入(最新合约价格/标记价格 <= stopPrice), 卖出(最新合约价格/标记价格 >= stopPrice)
        - TRAILING_STOP_MARKET 跟踪止损单: 买入(合约价格区间最低价格 < activationPrice 且最新合约价格 >= 最低价设定回调幅度), 卖出(合约价格区间最高价格 > activationPrice 且最新合约价格 <= 最高价设定回调幅度)
        
        如果 priceProtect 为 true，达到触发价时，MARK_PRICE 与 CONTRACT_PRICE 之间的价差不能超过 symbol 触发保护阈值。
        
        selfTradePreventionMode 仅在 timeInForce 为 IOC 或 GTC 或 GTD 时生效。
        
        响应示例:
        {
            "newClientStrategyId": "testOrder",
            "strategyId": 123445,
            "strategyStatus": "NEW",
            "strategyType": "TRAILING_STOP_MARKET", 
            "origQty": "10",
            "price": "0",
            "reduceOnly": false,
            "side": "BUY",
            "positionSide": "SHORT",
            "stopPrice": "9300",        
            "symbol": "BTCUSDT",
            "timeInForce": "GTD",
            "activatePrice": "9020",    
            "priceRate": "0.3",         
            "bookTime": 1566818724710,
            "updateTime": 1566818724722,
            "workingType": "CONTRACT_PRICE",
            "priceProtect": false, 
            "selfTradePreventionMode": "NONE",
            "goodTillDate": 1693207680000,
            "priceMatch": "NONE"          
        }
        """
        params = {
            'symbol': symbol,
            'side': side,
            'strategyType': strategyType,
        }
        
        if positionSide:
            params['positionSide'] = positionSide
        if timeInForce:
            params['timeInForce'] = timeInForce
        if quantity is not None:
            params['quantity'] = quantity
        if reduceOnly is not None:
            params['reduceOnly'] = reduceOnly
        if price is not None:
            params['price'] = price
        if workingType:
            params['workingType'] = workingType
        if priceProtect is not None:
            params['priceProtect'] = priceProtect
        if newClientStrategyId:
            params['newClientStrategyId'] = newClientStrategyId
        if stopPrice is not None:
            params['stopPrice'] = stopPrice
        if activationPrice is not None:
            params['activationPrice'] = activationPrice
        if callbackRate is not None:
            params['callbackRate'] = callbackRate
        if priceMatch:
            params['priceMatch'] = priceMatch
        if selfTradePreventionMode:
            params['selfTradePreventionMode'] = selfTradePreventionMode
        if goodTillDate:
            params['goodTillDate'] = goodTillDate
        
        params.update(kwargs)
        
        try:
            return self.post('/papi/v1/um/conditional/order', params=params, signed=True)
        except Exception as e:
            print(f"Error placing conditional order: {e}")
            raise
        
        
    def cancel_conditional_order(self, symbol, strategyId=None, newClientStrategyId=None, recvWindow=None):
        """
        取消UM条件订单 (TRADE)
        DELETE /papi/v1/um/conditional/order
        
        :param symbol: 交易对 (必需)
        :param strategyId: 策略ID (strategyId 与 newClientStrategyId 之一必须发送)
        :param newClientStrategyId: 用户自定义策略ID (strategyId 与 newClientStrategyId 之一必须发送)
        :param recvWindow: 接收窗口 (可选)
        """
        params = {
            'symbol': symbol
        }
        if strategyId:
            params['strategyId'] = strategyId
        if newClientStrategyId:
            params['newClientStrategyId'] = newClientStrategyId
        if recvWindow:
            params['recvWindow'] = recvWindow
        
        try:
            return self.delete('/papi/v1/um/conditional/order', params=params, signed=True)
        except Exception as e:
            print(f"Error canceling conditional order: {e}")
            raise
    def cancel_all_conditional_orders(self, symbol, recvWindow=None):
        """
        取消全部UM条件单 (TRADE)
        DELETE /papi/v1/um/conditional/allOpenOrders
        
        :param symbol: 交易对 (必需)
        :param recvWindow: 接收窗口 (可选)
        """
        params = {
            'symbol': symbol
        }
        if recvWindow:
            params['recvWindow'] = recvWindow
        
        try:
            return self.delete('/papi/v1/um/conditional/allOpenOrders', params=params, signed=True)
        except Exception as e:
            print(f"Error canceling all conditional orders: {e}")
            raise