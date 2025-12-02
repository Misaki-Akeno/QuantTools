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
        
        响应示例
        {
        "uniMMR": "5167.92171923",   // 统一账户维持保证金率
        "accountEquity": "73.47428058",   // 以USD计价的账户权益
        "actualEquity": "122607.35137903",   // 不考虑质押率的以USD计价账户权益
        "accountInitialMargin": "23.72469206", 
        "accountMaintMargin": "23.72469206", // 以USD计价统一账户维持保证金
        "accountStatus": "NORMAL"   // 统一账户账户状态："NORMAL", "MARGIN_CALL", "SUPPLY_MARGIN", "REDUCE_ONLY", "ACTIVE_LIQUIDATION", "FORCE_LIQUIDATION", "BANKRUPTED"
        "virtualMaxWithdrawAmount": "1627523.32459208"  // 以USD计价的最大可转出
        "totalAvailableBalance":"",
        "totalMarginOpenLoss":"", 
        "updateTime": 1657707212154 // 更新时间 
        }
        """
        return self.get('/papi/v1/account', signed=True)

    def get_um_account_info(self):
        """
        获取UM账户信息(USER_DATA)
        GET /papi/v1/um/account
        
        响应示例
        {   
        "assets": [
            {
                "asset": "USDT",            // 资产
                "crossWalletBalance": "23.72469206",      // 全仓账户余额
                "crossUnPnl": "0.00000000",    // 全仓持仓未实现盈亏
                "maintMargin": "0.00000000",   // 维持保证金
                "initialMargin": "0.00000000", // 当前所需起始保证金
                "positionInitialMargin": "0.00000000",  //持仓所需起始保证金(基于最新标记价格)
                "openOrderInitialMargin": "0.00000000", //当前挂单所需起始保证金(基于最新标记价格)
                "updateTime": 1625474304765 // 更新时间
            }
        ],
        "positions": [  // 头寸，将返回所有市场symbol。
            //根据用户持仓模式展示持仓方向，即单向模式下只返回BOTH持仓情况，双向模式下只返回 LONG 和 SHORT 持仓情况
            {
                "symbol": "BTCUSDT",    // 交易对
                "initialMargin": "0",   // 当前所需起始保证金(基于最新标记价格)
                "maintMargin": "0",     // 维持保证金
                "unrealizedProfit": "0.00000000",  // 持仓未实现盈亏
                "positionInitialMargin": "0",      //持仓所需起始保证金(基于最新标记价格)
                "openOrderInitialMargin": "0",     // 当前挂单所需起始保证金(基于最新标记价格)
                "leverage": "100",      // 杠杆倍率
                "entryPrice": "0.00000",    // 持仓成本价
                "maxNotional": "250000",    // 当前杠杆下用户可用的最大名义价值
                "bidNotional": "0",  // 买单净值，忽略
                "askNotional": "0",  // 卖单净值，忽略
                "positionSide": "BOTH",     // 持仓方向
                "positionAmt": "0",         //  持仓数量
                "updateTime": 0           // 更新时间
            }
        ]
    }
        """
        return self.get('/papi/v1/um/account', signed=True)

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