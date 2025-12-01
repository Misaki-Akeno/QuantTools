from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

class BinanceAPIError(Exception):
    """APIW错误响应包装。"""

    def __init__(self, status_code: int, message: str, payload: Optional[Any] = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.payload = payload

def stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        normalized = value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def drop_none(params: Mapping[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}
