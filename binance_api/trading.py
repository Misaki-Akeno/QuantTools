import json
from typing import Any, Dict, Optional, Sequence

from .client import BinanceClient
from .orders import OrderRequest


class BinanceDeliveryTrading:
    """交割合约交易接口封装。"""

    def __init__(self, client: BinanceClient, *, version_prefix: str = "/fapi/v1") -> None:
        self.client = client
        self.version_prefix = version_prefix.rstrip("/")

    def set_leverage(
        self,
        *,
        symbol: str,
        leverage: int,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        调整开仓杠杆 (TRADE)，对应 POST /fapi/v1/leverage，权重 1。

        Args:
            symbol: 交易对，例如 `BTCUSDT`。
            leverage: 1~125 的整数杠杆倍数。
            recv_window: 接口收敛窗口。
        """

        if leverage < 1 or leverage > 125:
            raise ValueError("leverage 需在 1~125 范围内。")
        params = {"symbol": symbol, "leverage": leverage}
        return self.client.signed_request(
            "POST",
            f"{self.version_prefix}/leverage",
            params=params,
            recv_window=recv_window,
        )

    def create_order(self, order: OrderRequest, *, recv_window: Optional[int] = None) -> Any:
        """
        下单 (TRADE)，对应 POST /fapi/v1/order，权重 1。

HTTP请求
POST /fapi/v1/order

请求权重
10s order rate limit(X-MBX-ORDER-COUNT-10S)为1; 1min order rate limit(X-MBX-ORDER-COUNT-1M)为1; IP rate limit(x-mbx-used-weight-1m)为0

请求参数
名称	类型	是否必需	描述
symbol	STRING	YES	交易对
side	ENUM	YES	买卖方向 SELL, BUY
positionSide	ENUM	NO	持仓方向，单向持仓模式下非必填，默认且仅可填BOTH;在双向持仓模式下必填,且仅可选择 LONG 或 SHORT
type	ENUM	YES	订单类型 LIMIT, MARKET, STOP, TAKE_PROFIT, STOP_MARKET, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
reduceOnly	STRING	NO	true, false; 非双开模式下默认false；双开模式下不接受此参数； 使用closePosition不支持此参数。
quantity	DECIMAL	NO	下单数量,使用closePosition不支持此参数。
price	DECIMAL	NO	委托价格
newClientOrderId	STRING	NO	用户自定义的订单号，不可以重复出现在挂单中。如空缺系统会自动赋值。必须满足正则规则 ^[\.A-Z\:/a-z0-9_-]{1,36}$
stopPrice	DECIMAL	NO	触发价, 仅 STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET 需要此参数
closePosition	STRING	NO	true, false；触发后全部平仓，仅支持STOP_MARKET和TAKE_PROFIT_MARKET；不与quantity合用；自带只平仓效果，不与reduceOnly 合用
activationPrice	DECIMAL	NO	追踪止损激活价格，仅TRAILING_STOP_MARKET 需要此参数, 默认为下单当前市场价格(支持不同workingType)
callbackRate	DECIMAL	NO	追踪止损回调比例，可取值范围[0.1, 10],其中 1代表1% ,仅TRAILING_STOP_MARKET 需要此参数
timeInForce	ENUM	NO	有效方法
workingType	ENUM	NO	stopPrice 触发类型: MARK_PRICE(标记价格), CONTRACT_PRICE(合约最新价). 默认 CONTRACT_PRICE
priceProtect	STRING	NO	条件单触发保护："TRUE","FALSE", 默认"FALSE". 仅 STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET 需要此参数
newOrderRespType	ENUM	NO	"ACK", "RESULT", 默认 "ACK"
priceMatch	ENUM	NO	OPPONENT/ OPPONENT_5/ OPPONENT_10/ OPPONENT_20/QUEUE/ QUEUE_5/ QUEUE_10/ QUEUE_20；不能与price同时传
selfTradePreventionMode	ENUM	NO	EXPIRE_TAKER/ EXPIRE_MAKER/ EXPIRE_BOTH； 默认NONE
goodTillDate	LONG	NO	TIF为GTD时订单的自动取消时间， 当timeInforce为GTD时必传；传入的时间戳仅保留秒级精度，毫秒级部分会被自动忽略，时间戳需大于当前时间+600s且小于253402300799000
recvWindow	LONG	NO	
timestamp	LONG	YES	
根据 order type的不同，某些参数强制要求，具体如下:

Type	强制要求的参数
LIMIT	timeInForce, quantity, price
MARKET	quantity
STOP, TAKE_PROFIT	quantity, price, stopPrice
STOP_MARKET, TAKE_PROFIT_MARKET	stopPrice
TRAILING_STOP_MARKET	callbackRate
条件单的触发必须:

如果订单参数priceProtect为true:
达到触发价时，MARK_PRICE(标记价格)与CONTRACT_PRICE(合约最新价)之间的价差不能超过改symbol触发保护阈值
触发保护阈值请参考接口GET /fapi/v1/exchangeInfo 返回内容相应symbol中"triggerProtect"字段
STOP, STOP_MARKET 止损单:
买入: 最新合约价格/标记价格高于等于触发价stopPrice
卖出: 最新合约价格/标记价格低于等于触发价stopPrice
TAKE_PROFIT, TAKE_PROFIT_MARKET 止盈单:
买入: 最新合约价格/标记价格低于等于触发价stopPrice
卖出: 最新合约价格/标记价格高于等于触发价stopPrice
TRAILING_STOP_MARKET 跟踪止损单:
买入: 当合约价格/标记价格区间最低价格低于激活价格activationPrice,且最新合约价格/标记价高于等于最低价设定回调幅度。
卖出: 当合约价格/标记价格区间最高价格高于激活价格activationPrice,且最新合约价格/标记价低于等于最高价设定回调幅度。
TRAILING_STOP_MARKET 跟踪止损单如果遇到报错 {"code": -2021, "msg": "Order would immediately trigger."}
表示订单不满足以下条件:

买入: 指定的activationPrice 必须小于 latest price
卖出: 指定的activationPrice 必须大于 latest price
newOrderRespType 如果传 RESULT:

MARKET 订单将直接返回成交结果；
配合使用特殊 timeInForce 的 LIMIT 订单将直接返回成交或过期拒绝结果。
STOP_MARKET, TAKE_PROFIT_MARKET 配合 closePosition=true:

条件单触发依照上述条件单触发逻辑
条件触发后，平掉当时持有所有多头仓位(若为卖单)或当时持有所有空头仓位(若为买单)
不支持 quantity 参数
自带只平仓属性，不支持reduceOnly参数
双开模式下,LONG方向上不支持BUY; SHORT 方向上不支持SELL
selfTradePreventionMode 仅在 timeInForce为IOC或GTC或GTD时生效.

极端行情时，timeInForce为GTD的订单自动取消可能有一定延迟

响应示例
{
 	"clientOrderId": "testOrder", // 用户自定义的订单号
 	"cumQty": "0",
 	"cumQuote": "0", // 成交金额
 	"executedQty": "0", // 成交量
 	"orderId": 22542179, // 系统订单号
 	"avgPrice": "0.00000",	// 平均成交价
 	"origQty": "10", // 原始委托数量
 	"price": "0", // 委托价格
 	"reduceOnly": false, // 仅减仓
 	"side": "SELL", // 买卖方向
 	"positionSide": "SHORT", // 持仓方向
 	"status": "NEW", // 订单状态
 	"stopPrice": "0", // 触发价，对`TRAILING_STOP_MARKET`无效
 	"closePosition": false,   // 是否条件全平仓
 	"symbol": "BTCUSDT", // 交易对
 	"timeInForce": "GTD", // 有效方法
 	"type": "TRAILING_STOP_MARKET", // 订单类型
 	"origType": "TRAILING_STOP_MARKET",  // 触发前订单类型
 	"activatePrice": "9020", // 跟踪止损激活价格, 仅`TRAILING_STOP_MARKET` 订单返回此字段
  	"priceRate": "0.3",	// 跟踪止损回调比例, 仅`TRAILING_STOP_MARKET` 订单返回此字段
 	"updateTime": 1566818724722, // 更新时间
 	"workingType": "CONTRACT_PRICE", // 条件价格触发类型
 	"priceProtect": false,            // 是否开启条件单触发保护
 	"priceMatch": "NONE",              //盘口价格下单模式
 	"selfTradePreventionMode": "NONE", //订单自成交保护模式
 	"goodTillDate": 1693207680000      //订单TIF为GTD时的自动取消时间
}
        """

        params = order.to_params()
        order_recv_window = params.pop("recvWindow", None)
        effective_recv_window = recv_window or order_recv_window
        return self.client.signed_request(
            "POST",
            f"{self.version_prefix}/order",
            params=params,
            recv_window=effective_recv_window,
        )

    def create_batch_orders(
        self,
        orders: Sequence[OrderRequest],
        *,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        批量下单 (TRADE)，对应 POST /fapi/v1/batchOrders，权重 5。

        限制与要点：
        - 一次最多 5 条订单，请求会并发处理，返回顺序与提交顺序一致。
        - 每个订单遵循与普通下单一致的必填/互斥规则。
        - `batchOrders` 需为 JSON 字符串，且不能携带 `recvWindow` 字段。

        Args:
            orders: 1~5 个 :class:`OrderRequest` 实例。
            recv_window: 全局 recvWindow。

        Raises:
            ValueError: 当订单数量超出 1~5 或为空时。
        """

        if not orders:
            raise ValueError("批量下单至少需要 1 个订单。")
        if len(orders) > 5:
            raise ValueError("批量下单最多支持 5 个订单。")

        payload = []
        for order in orders:
            params = order.to_params()
            params.pop("recvWindow", None)
            payload.append(params)

        return self.client.signed_request(
            "POST",
            f"{self.version_prefix}/batchOrders",
            params={"batchOrders": json.dumps(payload, separators=(",", ":"))},
            recv_window=recv_window,
        )

    def cancel_order(
        self,
        *,
        symbol: str,
        order_id: Optional[int] = None,
        orig_client_order_id: Optional[str] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        撤销订单 (TRADE)，对应 DELETE /fapi/v1/order，权重 1。

        Args:
            symbol: 交易对，例如 `BTCUSD_PERP`。
            order_id: 系统订单号。
            orig_client_order_id: 客户自定义订单号。
            recv_window: 接口收敛窗口。

        Raises:
            ValueError: order_id 与 orig_client_order_id 未提供任一时。
        """

        if not order_id and not orig_client_order_id:
            raise ValueError("撤单至少需要提供 order_id 或 orig_client_order_id。")

        params = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": orig_client_order_id,
        }
        return self.client.signed_request(
            "DELETE",
            f"{self.version_prefix}/order",
            params=params,
            recv_window=recv_window,
        )

    def cancel_batch_orders(
        self,
        *,
        symbol: str,
        order_id_list: Optional[Sequence[int]] = None,
        orig_client_order_id_list: Optional[Sequence[str]] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        批量撤销订单 (TRADE)，对应 DELETE /fapi/v1/batchOrders，权重 1。

        限制：
        - `orderIdList` 和 `origClientOrderIdList` 至少提供其一，且不可同时提供。
        - 每个列表最多 10 个条目，格式需为 JSON 数组字符串（官方示例 `[123,456]`）。

        Args:
            symbol: 交易对。
            order_id_list: 待撤销的系统订单号集合。
            orig_client_order_id_list: 待撤销的自定义订单号集合。
            recv_window: 收敛窗口。
        """

        if bool(order_id_list) == bool(orig_client_order_id_list):
            raise ValueError("order_id_list 与 orig_client_order_id_list 必须二选一。")

        payload: Dict[str, Any] = {"symbol": symbol}
        if order_id_list:
            if len(order_id_list) > 10:
                raise ValueError("order_id_list 最多支持 10 个订单。")
            payload["orderIdList"] = json.dumps(list(order_id_list), separators=(",", ":"))
        if orig_client_order_id_list:
            if len(orig_client_order_id_list) > 10:
                raise ValueError("orig_client_order_id_list 最多支持 10 个订单。")
            payload["origClientOrderIdList"] = json.dumps(
                list(orig_client_order_id_list),
                separators=(",", ":"),
            )

        return self.client.signed_request(
            "DELETE",
            f"{self.version_prefix}/batchOrders",
            params=payload,
            recv_window=recv_window,
        )

    def cancel_all_orders(self, *, symbol: str, recv_window: Optional[int] = None) -> Any:
        """
        撤销指定交易对的全部挂单 (TRADE)，对应 DELETE /fapi/v1/allOpenOrders，权重 1。

        Args:
            symbol: 交易对。
            recv_window: 收敛窗口。
        """

        return self.client.signed_request(
            "DELETE",
            f"{self.version_prefix}/allOpenOrders",
            params={"symbol": symbol},
            recv_window=recv_window,
        )

    def countdown_cancel_all(
        self,
        *,
        symbol: str,
        countdown_time: int,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        倒计时撤销所有订单 (TRADE)，对应 POST /fapi/v1/countdownCancelAll，权重 10。

        官方推荐将该接口作为“心跳”，在 countdown 内重复调用以刷新倒计时。
        countdownTime 单位为毫秒，0 表示终止倒计时。

        Args:
            symbol: 需要保护的交易对。
            countdown_time: 倒计时毫秒数 (>=0)。
            recv_window: 收敛窗口。
        """

        if countdown_time < 0:
            raise ValueError("countdown_time 不能为负数。")

        params = {"symbol": symbol, "countdownTime": countdown_time}
        return self.client.signed_request(
            "POST",
            f"{self.version_prefix}/countdownCancelAll",
            params=params,
            recv_window=recv_window,
        )

    def get_order(
        self,
        *,
        symbol: str,
        order_id: Optional[int] = None,
        orig_client_order_id: Optional[str] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查询订单状态 (USER_DATA)，对应 GET /fapi/v1/order，权重 1。

        注意：官方对可查询的订单有时间限制（取消未成交单 3 天后不可查，所有订单 90 天后不可查）。

        Args:
            symbol: 交易对。
            order_id: 系统订单号。
            orig_client_order_id: 客户自定义订单号。
            recv_window: 收敛窗口。

        Raises:
            ValueError: order_id 与 orig_client_order_id 均未提供时。
        """

        if not order_id and not orig_client_order_id:
            raise ValueError("查询订单时必须至少提供 order_id 或 orig_client_order_id 之一。")
        params = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": orig_client_order_id,
        }
        return self.client.signed_request(
            "GET",
            f"{self.version_prefix}/order",
            params=params,
            recv_window=recv_window,
        )

    def get_all_orders(
        self,
        *,
        symbol: Optional[str] = None,
        pair: Optional[str] = None,
        order_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查询所有订单（含历史）(USER_DATA)，对应 GET /fapi/v1/allOrders。

        规则概要：
        - `symbol` 与 `pair` 必须二选一，且不能同时传递。
        - `orderId` 仅在搭配 `symbol` 时生效，用于游标式向后查询。
        - 查询窗口最大 7 天，缺省为最近 7 天。
        - 请求权重：带 symbol 为 20，带 pair 为 40。

        Args:
            symbol: 具体交易对。
            pair: 标的交易对。
            order_id: 仅返回该 ID 及之后的订单。
            start_time: 起始毫秒时间戳。
            end_time: 结束毫秒时间戳。
            limit: 返回条数 (默认 50, 最大 100)。
            recv_window: 收敛窗口。
        """

        if bool(symbol) == bool(pair):
            raise ValueError("symbol 与 pair 必须二选一。")
        if pair and order_id:
            raise ValueError("使用 pair 查询时不可同时传 order_id。")

        params = {
            "symbol": symbol,
            "pair": pair,
            "orderId": order_id,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self.client.signed_request(
            "GET",
            f"{self.version_prefix}/allOrders",
            params=params,
            recv_window=recv_window,
        )

    def get_open_orders(
        self,
        *,
        symbol: Optional[str] = None,
        pair: Optional[str] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查看当前全部挂单 (USER_DATA)，对应 GET /fapi/v1/openOrders。

        - 不带 symbol/pair 取全部挂单，权重 40；带 symbol 权重 1。
        - 为避免歧义，请勿同时传 symbol 与 pair。

        Args:
            symbol: 指定交易对。
            pair: 指定标的交易对。
            recv_window: 收敛窗口。
        """

        if symbol and pair:
            raise ValueError("openOrders 查询请勿同时传 symbol 与 pair。")

        params = {"symbol": symbol, "pair": pair}
        return self.client.signed_request(
            "GET",
            f"{self.version_prefix}/openOrders",
            params=params,
            recv_window=recv_window,
        )

    def get_open_order(
        self,
        *,
        symbol: str,
        order_id: Optional[int] = None,
        orig_client_order_id: Optional[str] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查询当前挂单 (USER_DATA)，对应 GET /fapi/v1/openOrder，权重 1。

        注意：仅支持未成交的挂单；若订单已成交或已取消，将返回 "Order does not exist."。

        Args:
            symbol: 交易对。
            order_id: 系统订单号。
            orig_client_order_id: 客户自定义订单号。
            recv_window: 收敛窗口。
        """

        if not order_id and not orig_client_order_id:
            raise ValueError("查询挂单需提供 order_id 或 orig_client_order_id。")

        params = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": orig_client_order_id,
        }
        return self.client.signed_request(
            "GET",
            f"{self.version_prefix}/openOrder",
            params=params,
            recv_window=recv_window,
        )

    def get_position_risk(
        self,
        *,
        margin_asset: Optional[str] = None,
        pair: Optional[str] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查询用户持仓风险 (USER_DATA)，对应 GET /fapi/v1/positionRisk，权重 1。

        - `marginAsset` 与 `pair` 不可同时提供；均为空时返回所有上市/结算中 symbol。
        - 双向持仓会返回 BOTH/LONG/SHORT 三个方向；单向持仓仅返回 BOTH。

        Args:
            margin_asset: 保证金币种过滤。
            pair: 标的交易对过滤。
            recv_window: 收敛窗口。
        """

        if margin_asset and pair:
            raise ValueError("margin_asset 与 pair 不可同时提供。")

        params = {"marginAsset": margin_asset, "pair": pair}
        return self.client.signed_request(
            "GET",
            f"{self.version_prefix}/positionRisk",
            params=params,
            recv_window=recv_window,
        )

    def get_user_trades(
        self,
        *,
        symbol: str,
        order_id: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        from_id: Optional[int] = None,
        limit: Optional[int] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查询账户成交历史 (USER_DATA)，对应 GET /fapi/v1/userTrades 或 /dapi/v1/userTrades，权重 5。

        Args:
            symbol: 交易对。
            order_id: 过滤指定订单及之后的成交，仅在 symbol 模式下可用。
            start_time: 起始毫秒时间戳，最大窗口 7 天。
            end_time: 结束毫秒时间戳。
            from_id: 交易 ID 游标，返回该 ID 及之后的成交。
            limit: 返回条数，默认 500，最大 1000。
            recv_window: 收敛窗口。
        """

        params = {
            "symbol": symbol,
            "orderId": order_id,
            "startTime": start_time,
            "endTime": end_time,
            "fromId": from_id,
            "limit": limit,
        }
        return self.client.signed_request(
            "GET",
            f"{self.version_prefix}/userTrades",
            params=params,
            recv_window=recv_window,
        )
