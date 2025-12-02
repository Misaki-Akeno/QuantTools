本项目提供了对Binance交易所API的访问和交互功能。

## 重要警告，请每次运行复述
修改代码之后禁止直接运行，现在使用的是生产api。
使用try必须捕获异常并提示处理。
使用uv run python <script.py> 运行代码。

## 一般信息
账户是生产账户
账户是单向持仓模式，减仓使用reduceonly
请只使用ETHUSDC交易对

## 主要需要的api接口
下面提供的接口如果没有在代码中实现，我只写了UM相关接口，可以告诉我。
### https://papi.binance.com
提供统一账户账户信息查询，u本位期货交易功能。
### 交易接口
UM下单(TRADE)
UM条件单下单(TRADE)
撤销UM订单(TRADE)
撤销全部UM订单 (TRADE)
取消UM条件订单(TRADE)
取消全部UM条件单(TRADE)
修改UM订单(TRADE)
查询UM订单(USER-DATA)
查询所有UM订单(包括历史订单) (USER-DATA)
查询当前UM挂单(USER-DATA)
查看当前全部UM挂单(USER-DATA)
查询UM所有条件订单(TRADE)
查看UM当前全部条件挂单(USER-DATA)
查询UM当前条件挂单(USER-DATA)
查询UM条件单历史(USER-DATA)
用户强平单历史(USER-DATA)
查询CM订单修改历史(USER_DATA)
UM账户成交历史(USER-DATA)
UM持仓ADL队列估算(USER-DATA)
### 账户接口
查询账户余额(USER-DATA)
查询账户信息(USER-DATA)
查询账户最大可借贷额度 (USER-DATA)
查询账户最大可转出额度(USER-DATA)
用户 UM 持仓风险(USER-DATA)
调整UM开仓杠杆(TRADE)
更改UM持仓模式(TRADE)
查询UM持仓模式(USER-DATA)
查询UM杠杆分层标准 (USER-DATA)
统一账户UM合约交易量化规则指标(USER-DATA)
查询用户UM手续费率(USER-DATA)
查询杠杆借贷记录(USER-DATA)
查询杠杆还贷记录(USER-DATA)
查询自动清还合约负余额模式(USER-DATA)
更改自动清还合约负余额模式(TRADE)
获取杠杆利息历史(USER_DATA)
清还合约负余额(USER-DATA)
查询统一账户期货负余额收息历史(USER-DATA)
统一账户资金归集(TRADE)
特定资产资金归集(TRADE)
BNB划转(TRADE)
获取UM损益资金流水(USER-DATA)
获取UM账户信息(USER-DATA)
UM账户配置(USER-DATA)
UM合约交易对配置(USER-DATA)
获取UM账户信息V2(USER-DATA)
获取UM合约交易历史下载Id(USER-DATA)
通过下载Id获取UM合约交易历史下载链接(USER-DATA)
获取UM合约订单历史下载Id(USER-DATA)
通过下载Id获取UM合约订单历史下载链接(USER-DATA)
获取UM合约资金流水历史下载Id(USER-DATA)
通过下载Id获取UM合约资金流水历史下载链接(USER-DATA)
查询用户下单限频(USER-DATA)
查询用户负余额自动兑换记录(USER-DATA)

### https://fapi.binance.com
提供u本位期货信息查询，注意这里不可以交易，因为账户是统一账户。

测试服务器连通性PING
获取服务器时间
获取交易规则和交易对
合约下架日期
深度信息
RPI深度信息
近期成交
查询历史成交(MARKET-DATA)
近期成交(归集)
K 线数据
连续合约 K 线数据
价格指数K线数据
标记价格K线数据
溢价指数K线数据
最新标记价格和资金费率
查询资金费率历史
查询资金费率信息
24hr价格变动情况
最新价格(已弃用)
最新价格V2
当前最优挂单
季度合约历史结算价
获取未平仓合约数
合约持仓量历史
大户持仓量多空比
大户账户数多空比
多空持仓人数比
合约主动买卖量
基差
综合指数交易对信息
多资产模式资产汇率指数
查询指数价格成分
查询保险基金余额快照
自动减仓风险评级


## 其他信息
### 基本信息
IP 访问限制
每个请求将包含一个X-MBX-USED-权重-(intervalNum)(intervalLetter)的头，其中包含当前IP所有请求的已使用权重。
每个路由都有一个"权重"，该权重确定每个接口计数的请求数。较重的接口和对多个交易对进行操作的接口将具有较重的"权重"。
收到429时，您有责任作为API退回而不向其发送更多的请求。
如果屡次违反速率限制和/或在收到429后未能退回，将导致API的IP被禁(http状态418)。
频繁违反限制，封禁时间会逐渐延长 ，对于重复违反者，将会被封从2分钟到3天。
访问限制是基于IP的，而不是API Key
统一账户IP访问频率限制为6000/min。
强烈建议您尽可能多地使用websocket消息获取相应数据,既可以保障消息的及时性，也可以减少请求带来的访问限制压力。
下单频率限制
每个下单请求回报将包含一个X-MBX-ORDER-COUNT-(intervalNum)(intervalLetter)的头，其中包含当前账户已用的下单限制数量。
被拒绝或不成功的下单并不保证回报中包含以上头内容。
下单频率限制是基于每个账户计数的。
统一账户下单频率限制为1200/min。
接口鉴权类型
每个接口都有自己的鉴权类型，鉴权类型决定了访问时应当进行何种鉴权
如果需要 API-key，应当在HTTP头中以X-MBX-APIKEY字段传递
API-key 与 API-secret 是大小写敏感的
可以在网页用户中心修改API-key 所具有的权限，例如读取账户信息、发送交易指令、发送提现指令
鉴权类型	描述
NONE	不需要鉴权的接口
TRADE	需要有效的API-KEY和签名
USER_DATA	需要有效的API-KEY和签名
USER_STREAM	需要有效的API-KEY
MARKET_DATA	需要有效的API-KEY

### 公开API参数
术语解释
base asset 指一个交易对的交易对象，即写在靠前部分的资产名
quote asset 指一个交易对的定价资产，即写在靠后部分资产名
Margin 指全仓杠杆
UM 指U本位合约USD-M Futures
CM 指币本位合约Coin-M Futures
枚举定义
订单方向 (side):

BUY 买入
SELL 卖出
合约持仓方向:

BOTH 单一持仓方向
LONG 多头(双向持仓下)
SHORT 空头(双向持仓下)
有效方式 (timeInForce):

GTC - Good Till Cancel 成交为止
IOC - Immediate or Cancel 无法立即成交(吃单)的部分就撤销
FOK - Fill or Kill 无法全部立即成交就撤销
GTX - Good Till Crossing 无法成为挂单方就撤销
响应类型 (newOrderRespType)

ACK
RESULT
订单种类 (orderTypes, type):

LIMIT
MAERKET
条件订单类型（type）:

STOP
STOP_MARKET
TAKE_PROFIT
TAKE_PROFIT_MARKET
TRAILING_STOP_MARKET
合约条件单价格触发类型 (workingType)

MARK_PRICE 标记价格
条件单状态 (strategyStatus)

NEW
CANCELED
TRIGGERED - 条件单被触发
FINISHED - 触发单完全成交
EXPIRED
合约类型 (contractType):

PERPETUAL 永续合约
CURRENT_MONTH 当月交割合约
NEXT_MONTH 次月交割合约
CURRENT_QUARTER 当季交割合约
NEXT_QUARTER 次季交割合约
PERPETUAL_DELIVERING 交割结算中合约
合约状态 (contractStatus, status):

PENDING_TRADING 待上市
TRADING 交易中
PRE_DELIVERING 预交割
DELIVERING 交割中
DELIVERED 已交割
PRE_SETTLE 预结算
SETTLING 结算中
CLOSE 已下架
订单状态 (status):

NEW 新建订单
PARTIALLY_FILLED 部分成交
FILLED 全部成交
CANCELED 已撤销
REJECTED 订单被拒绝
EXPIRED 订单过期(根据timeInForce参数规则)
限制种类 (rateLimitType)

REQUEST_权重

  {
  	"rateLimitType": "REQUEST_权重",
  	"interval": "MINUTE",
  	"intervalNum": 1,
  	"limit": 2400
  }

ORDERS

  {
  	"rateLimitType": "ORDERS",
  	"interval": "MINUTE",
  	"intervalNum": 1,
  	"limit": 1200
   }

REQUESTS_权重 单位时间请求权重之和上限

ORDERS 单位时间下单(撤单)次数上限

限制间隔

MINUTE
过滤器
过滤器，即Filter，定义了一系列交易规则。 共有两类，分别是针对交易对的过滤器symbol filters，和针对整个交易所的过滤器exchange filters(暂不支持)

交易对过滤器
PRICE_FILTER 价格过滤器
/exchangeInfo 响应中的格式:

  {
    "filterType": "PRICE_FILTER",
    "minPrice": "0.00000100",
    "maxPrice": "100000.00000000",
    "tickSize": "0.00000100"
  }

价格过滤器用于检测order订单中price参数的合法性

minPrice 定义了 price/stopPrice 允许的最小值
maxPrice 定义了 price/stopPrice 允许的最大值。
tickSize 定义了 price/stopPrice 的步进间隔，即price必须等于minPrice+(tickSize的整数倍) 以上每一项均可为0，为0时代表这一项不再做限制。
逻辑伪代码如下：

price >= minPrice
price <= maxPrice
(price-minPrice) % tickSize == 0
LOT_SIZE 订单尺寸
/exchangeInfo 响应中的格式:*

  {
    "filterType": "LOT_SIZE",
    "minQty": "0.00100000",
    "maxQty": "100000.00000000",
    "stepSize": "0.00100000"
  }

lots是拍卖术语，这个过滤器对订单中的quantity也就是数量参数进行合法性检查。包含三个部分：

minQty 表示 quantity 允许的最小值.
maxQty 表示 quantity 允许的最大值
stepSize 表示 quantity允许的步进值。
逻辑伪代码如下：

quantity >= minQty
quantity <= maxQty
(quantity-minQty) % stepSize == 0
MARKET_LOT_SIZE 市价订单尺寸
参考LOT_SIZE，区别仅在于对市价单还是限价单生效

MAX_NUM_ORDERS 最多订单数
/exchangeInfo 响应中的格式:

  {
    "filterType": "MAX_NUM_ORDERS",
    "limit": 200
  }

定义了某个交易对最多允许的挂单数量(不包括已关闭的订单)

普通订单与条件订单均计算在内

MAX_NUM_ALGO_ORDERS 最多条件订单数
/exchangeInfo format:

  {
    "filterType": "MAX_NUM_ALGO_ORDERS",
    "limit": 100
  }

定义了某个交易对最多允许的条件订单的挂单数量(不包括已关闭的订单)。

条件订单目前包括STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, 和 TRAILING_STOP_MARKET

PERCENT_PRICE 价格振幅过滤器
/exchangeInfo 响应中的格式:

  {
    "filterType": "PERCENT_PRICE",
    "multiplierUp": "1.1500",
    "multiplierDown": "0.8500",
    "multiplierDecimal": 4
  }

PERCENT_PRICE 定义了基于标记价格计算的挂单价格的可接受区间.

挂单价格必须同时满足以下条件：

买单: price <= markPrice * multiplierUp
卖单: price >= markPrice * multiplierDown
MIN_NOTIONAL 最小名义价值
/exchangeInfo 响应中的格式:

  {
    "filterType": "MIN_NOTIONAL",
    "notioanl": "5.0"
  }

MIN_NOTIONAL过滤器定义了交易对订单所允许的最小名义价值(成交额)。 订单的名义价值是价格*数量。 由于MARKET订单没有价格，因此会使用 mark price 计算。