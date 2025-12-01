import hashlib
import hmac
import os
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

from .utils import BinanceAPIError, drop_none, stringify


class BinanceClient:
    """轻量级的币安 U 本位合约 HTTP 客户端，负责签名与请求发送。"""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str,
        *,
        timeout: int = 10,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        if self.api_key:
            self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def _sign(self, query_string: str) -> str:
        return hmac.new(self.api_secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

    def _fetch_server_time(self) -> int:
        last_error: Optional[BinanceAPIError] = None
        for path in ("/fapi/v1/time", "/dapi/v1/time"):
            try:
                data = self._request("GET", path)
            except BinanceAPIError as exc:
                last_error = exc
                continue
            if isinstance(data, Mapping) and "serverTime" in data:
                try:
                    return int(data["serverTime"])
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(f"服务器时间格式错误: {data}") from exc
        if last_error:
            raise RuntimeError("无法获取服务器时间。") from last_error
        raise RuntimeError("无法获取服务器时间。")

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, params=params, timeout=self.timeout)
        if response.status_code >= 400:
            payload: Any
            try:
                payload = response.json()
                message = payload.get("msg") or payload
            except ValueError:
                payload = response.text
                message = payload
            raise BinanceAPIError(response.status_code, str(message), payload=payload)
        if not response.content:
            return None
        try:
            data = response.json()
        except ValueError:
            data = response.text
        return data

    def public_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        formatted_params = {k: stringify(v) for k, v in drop_none(params or {}).items()}
        return self._request(method, path, params=formatted_params)

    def signed_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        recv_window: Optional[int] = None,
        timestamp: Optional[int] = None,
    ) -> Any:
        params_dict = dict(params) if params else {}
        if recv_window is not None:
            params_dict.setdefault("recvWindow", recv_window)
        server_time = self._fetch_server_time()
        params_dict.setdefault("timestamp", timestamp or server_time)

        formatted_params = {k: stringify(v) for k, v in drop_none(params_dict).items()}
        query_string = urlencode(formatted_params, doseq=True)
        signature = self._sign(query_string)
        
        # 手动拼接 signature 确保其在最后，符合 Binance 接口要求
        if query_string:
            full_query = f"{query_string}&signature={signature}"
        else:
            full_query = f"signature={signature}"
            
        # 将拼接好的 query string 直接附加到 path，避免 requests 重新排序或编码
        return self._request(method, f"{path}?{full_query}", params=None)

def build_client_from_env(prod: bool = False) -> BinanceClient:
    load_dotenv(".env.local")
    if prod:
        api_key = os.getenv("API_KEY_PROD", "")
        api_secret = os.getenv("SECRET_KEY_PROD", "")
        base_url = os.getenv("BASE_URL_PROD", "https://fapi.binance.com")
    else:
        api_key = os.getenv("API_KEY", "")
        api_secret = os.getenv("SECRET_KEY", "")
        base_url = os.getenv("BASE_URL_TEST", "")

    if not all([api_key, api_secret, base_url]):
        env_name = "生产" if prod else "测试"
        raise RuntimeError(f"缺少 {env_name} 环境的 API Key、Secret 或 Base URL，请检查 .env.local 配置。")
    return BinanceClient(api_key, api_secret, base_url)
