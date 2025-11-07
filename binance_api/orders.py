from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any, ClassVar, Dict, Mapping, Optional

from .utils import stringify


@dataclass
class OrderRequest:
    """交割合约 /fapi/v1/order 请求构造器与校验器。"""

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
