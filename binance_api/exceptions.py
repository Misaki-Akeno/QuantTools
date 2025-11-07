from typing import Any, Optional


class BinanceAPIError(Exception):
    """API错误响应包装。"""

    def __init__(self, status_code: int, message: str, payload: Optional[Any] = None) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.payload = payload
