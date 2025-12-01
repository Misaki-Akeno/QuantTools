import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, ClassVar, Dict, Mapping, Optional, Sequence

from .client import BinanceClient
from .utils import stringify


@dataclass
class OrderRequest:
    """U 本位合约 /fapi/v1/order 请求构造器与校验器。"""

    symbol: str
    side: str
    order_type: str
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    position_side: Optional[str] = None
    reduce_only: Optional[bool] = None
    new_client_order_id: Optional[str] = None
    stop_price: Optional[Decimal] = None
    close_position: Optional[bool] = None
    activation_price: Optional[Decimal] = None
    callback_rate: Optional[Decimal] = None
    time_in_force: Optional[str] = None
    working_type: Optional[str] = None
    price_protect: Optional[bool] = None
    new_order_resp_type: Optional[str] = None
    price_match: Optional[str] = None
    self_trade_prevention_mode: Optional[str] = None
    recv_window: Optional[int] = 5000
    extra_params: Dict[str, Any] = field(default_factory=dict)

    _ATTR_TO_PARAM: ClassVar[Mapping[str, str]] = {
        "order_type": "type",
        "position_side": "positionSide",
        "reduce_only": "reduceOnly",
        "new_client_order_id": "newClientOrderId",
        "stop_price": "stopPrice",
        "close_position": "closePosition",
        "activation_price": "activationPrice",
        "callback_rate": "callbackRate",
        "time_in_force": "timeInForce",
        "working_type": "workingType",
        "price_protect": "priceProtect",
        "new_order_resp_type": "newOrderRespType",
        "price_match": "priceMatch",
        "self_trade_prevention_mode": "selfTradePreventionMode",
        "recv_window": "recvWindow",
    }

    _REQUIRED_BY_TYPE: ClassVar[Mapping[str, set[str]]] = {
        "LIMIT": {"quantity", "price", "timeInForce"},
        "MARKET": {"quantity"},
        "STOP": {"quantity", "price", "stopPrice"},
        "TAKE_PROFIT": {"quantity", "price", "stopPrice"},
        "STOP_MARKET": {"stopPrice"},
        "TAKE_PROFIT_MARKET": {"stopPrice"},
        "TRAILING_STOP_MARKET": {"callbackRate"},
    }

    _BOOLEAN_OVERRIDES: ClassVar[Mapping[str, Any]] = {
        "reduceOnly": lambda value: "true" if value else "false",
        "closePosition": lambda value: "true" if value else "false",
        "priceProtect": lambda value: "TRUE" if value else "FALSE",
    }

    def validate(self) -> None:
        order_type_key = self.order_type.upper()
        required_params = self._REQUIRED_BY_TYPE.get(order_type_key, set())
        provided_params = self._gather_params()
        missing = [param for param in required_params if param not in provided_params]
        if missing:
            raise ValueError(f"订单类型 {order_type_key} 需要参数: {', '.join(missing)}")

        if self.close_position and self.quantity is not None:
            raise ValueError("closePosition 与 quantity 不能同时使用。")
        if self.close_position and self.reduce_only:
            raise ValueError("closePosition 已隐含 reduceOnly，无需重复设置。")
        if self.price and self.price_match:
            raise ValueError("priceMatch 不可与 price 同时提交。")

    def _gather_params(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for attr, value in asdict(self, dict_factory=dict).items():
            if attr in {"extra_params"}:
                continue
            if value is None:
                continue
            param_name = self._ATTR_TO_PARAM.get(attr, attr)
            payload[param_name] = value
        payload.update(self.extra_params)
        return payload

    def to_params(self) -> Dict[str, Any]:
        self.validate()
        params: Dict[str, Any] = {}
        for key, value in self._gather_params().items():
            if key in self._BOOLEAN_OVERRIDES:
                params[key] = self._BOOLEAN_OVERRIDES[key](value)
            else:
                params[key] = stringify(value)
        return params


class BinanceTrading:
    """U 本位合约交易接口封装。"""

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
        symbol: Optional[str] = None,
        recv_window: Optional[int] = None,
    ) -> Any:
        """
        查询持仓风险 (USER_DATA)，对应 GET /fapi/v3/positionRisk 或 /dapi/v3/positionRisk。

        Args:
            symbol: 交易对过滤，仅返回指定合约的风险信息。
            recv_window: 收敛窗口。
        """

        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self.client.signed_request(
            "GET",
            self._position_risk_endpoint(),
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

    def _position_risk_endpoint(self) -> str:
        if self.version_prefix.endswith("/v1"):
            return f"{self.version_prefix[:-3]}/v3/positionRisk"
        return f"{self.version_prefix}/positionRisk"
